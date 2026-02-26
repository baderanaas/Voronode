"""
Voronode — AI Assistant (main page)

Unified chat + document upload interface. This is the default page
that opens when the app starts.
"""

import streamlit as st
import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
from datetime import datetime

frontend_path = Path(__file__).parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient

st.set_page_config(
    page_title="Voronode",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

api = APIClient()

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [
    ("chat_messages", []),
    ("session_id", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"),
    ("pending_input", None),  # {user_input, pending_files, history} while processing
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helpers ───────────────────────────────────────────────────────────────────


def render_assistant_message(msg: dict):
    """Render assistant message text + optional structured data."""
    if msg.get("content"):
        st.markdown(msg["content"])

    display_data = msg.get("display_data")
    display_format = msg.get("display_format", "text")

    if not display_data:
        return

    if display_format == "table" and "rows" in display_data:
        st.markdown("---")
        st.dataframe(pd.DataFrame(display_data["rows"]), use_container_width=True)
        if "summary" in display_data:
            st.info(f"📊 {display_data['summary']}")

    elif display_format == "chart":
        st.markdown("---")
        chart_type = display_data.get("chart_type", "bar")
        if chart_type == "bar":
            fig = px.bar(
                x=display_data.get("x_axis", []), y=display_data.get("y_axis", [])
            )
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "line":
            fig = px.line(
                x=display_data.get("x_axis", []), y=display_data.get("y_axis", [])
            )
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "pie":
            fig = px.pie(
                values=display_data.get("y_axis", []),
                names=display_data.get("labels", []),
            )
            st.plotly_chart(fig, use_container_width=True)
        if "summary" in display_data:
            st.info(f"📊 {display_data['summary']}")

    if "metadata" in display_data:
        with st.expander("🔍 Execution details"):
            meta = display_data["metadata"]
            c1, c2, c3 = st.columns(3)
            if "execution_time" in meta:
                c1.metric("⏱️ Time", f"{meta['execution_time']:.2f}s")
            if "tools_used" in meta:
                c2.metric("🔧 Tools", len(meta["tools_used"]))
            if "record_count" in meta:
                c3.metric("📝 Records", meta["record_count"])


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 💡 Example questions")
    examples = [
        "Show me all invoices over $50,000",
        "Which contractor has the most violations?",
        "What's the budget variance for PRJ-001?",
        "Find all overdue invoices",
        "Total retention across all contracts",
        "Which projects are over budget?",
        "Check compliance for CONTRACT-001",
    ]
    for example in examples:
        if st.button(f"📝 {example}", key=example, use_container_width=True):
            st.session_state.example_query = example

    st.markdown("---")
    if st.button("🗑️ Clear conversation", use_container_width=True):
        st.session_state.chat_messages = []
        st.session_state.pending_input = None
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ How it works")
    st.markdown(
        """
    **Planner** → routes your query
    **Executor** → queries Neo4j, ChromaDB, compliance
    **Validator** → checks answer quality
    **Responder** → formats the result

    Attach documents using the 📎 button to ingest them,
    then ask questions about them in the same thread.
    """
    )


# ── Title ─────────────────────────────────────────────────────────────────────
st.title("💬 Assistant")

# ── Chat history ──────────────────────────────────────────────────────────────
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            attachments = msg.get("attachments", [])
            if attachments:
                names_html = " ".join(
                    f"<span style='font-size:0.85rem;color:#888;'>📎 {n}</span>"
                    for n in attachments
                )
                st.markdown(names_html, unsafe_allow_html=True)
            if msg.get("content"):
                st.markdown(msg["content"])
        else:
            render_assistant_message(msg)

# ── Welcome message (shown only on empty chat while not processing) ────────────
if not st.session_state.chat_messages and st.session_state.pending_input is None:
    with st.chat_message("assistant"):
        st.markdown(
            """
        👋 **Welcome — I'm your financial risk management assistant.**

        I can help you:
        - 📊 Query invoices, contracts, budgets, and projects
        - 🔍 Detect compliance violations and anomalies
        - 💰 Calculate financial metrics and variances
        - ⚠️ Identify risks across your project portfolio

        Use the 📎 button to attach a document and ingest it, or just ask a question.
        """
        )

# ── In-flight assistant response (renders ABOVE the chat input bar) ───────────
# This block is entered on the rerun immediately after user submission.
# It runs the SSE loop synchronously and renders the response in the correct
# position (below the last user message, above the fixed chat input).
if st.session_state.pending_input is not None:
    pi = st.session_state.pending_input

    with st.chat_message("assistant"):
        n_files = len(pi["pending_files"])
        initial_label = f"Processing {n_files} file(s)..." if n_files else "Thinking..."
        stage_placeholder = st.empty()
        stage_placeholder.markdown(f"_{initial_label}_")

        response_text = ""
        display_format = "text"
        display_data = None
        processing_time = None

        try:
            for event in api.stream(
                message=pi["user_input"] or "",
                files=pi["pending_files"] or None,
                conversation_history=pi["history"],
                session_id=st.session_state.session_id,
            ):
                etype = event.get("event", "")
                data = event.get("data", {})

                if etype == "planner":
                    stage_placeholder.markdown(
                        "_Classifying documents..._"
                        if data.get("route") == "upload_plan"
                        else "_Planning query..._"
                    )
                elif etype == "upload_agent":
                    stage_placeholder.markdown("_Saving to graph..._")
                elif etype == "upload_summary":
                    stage_placeholder.markdown("_Formatting..._")
                    response_text = data.get("response", response_text)
                    display_format = data.get("display_format", "text")
                    display_data = data.get("display_data")
                elif etype == "executor":
                    stage_placeholder.markdown("_Querying data..._")
                elif etype == "validator":
                    stage_placeholder.markdown("_Reviewing answer..._")
                elif etype == "responder":
                    stage_placeholder.markdown("_Formatting..._")
                    response_text = data.get("response", response_text)
                    if data.get("display_data") is not None:
                        display_format = data.get("display_format", "text")
                        display_data = data.get("display_data")
                elif etype == "complete":
                    processing_time = data.get("processing_time_seconds")
                elif etype == "error":
                    err = data.get("message", data.get("error", "Unknown error"))
                    stage_placeholder.empty()
                    st.error(err)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": f"Error: {err}"}
                    )
                    st.session_state.pending_input = None
                    st.rerun()

            stage_placeholder.empty()
            assistant_msg = {
                "role": "assistant",
                "content": response_text,
                "display_format": display_format,
                "display_data": display_data,
            }
            render_assistant_message(assistant_msg)
            st.session_state.chat_messages.append(assistant_msg)
            if processing_time is not None:
                st.caption(f"⏱️ {processing_time:.2f}s")

        except Exception as e:
            stage_placeholder.empty()
            st.error(f"Error: {e}")
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": f"Error: {e}"}
            )

    st.session_state.pending_input = None
    st.rerun()


# ── Chat input (fixed at the bottom of the viewport) ─────────────────────────
response = st.chat_input(
    "Ask a question about invoices, contracts, budgets, or projects...",
    accept_file="multiple",
    file_type=["pdf", "xlsx", "xls", "csv"],
)

# Sidebar example → queue as pending input
if "example_query" in st.session_state:
    example_text = st.session_state.pop("example_query")
    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.chat_messages
        if m.get("content")
    ]
    st.session_state.chat_messages.append({"role": "user", "content": example_text})
    st.session_state.pending_input = {
        "user_input": example_text,
        "pending_files": [],
        "history": history,
    }
    st.rerun()

# New submission from the chat input widget
if response:
    user_text = response.text or ""
    pending_files = [
        {"bytes": uf.read(), "name": uf.name} for uf in (response.files or [])
    ]

    if not user_text and not pending_files:
        st.stop()

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.chat_messages
        if m.get("content")
    ]
    user_msg: dict = {"role": "user", "content": user_text}
    if pending_files:
        user_msg["attachments"] = [f["name"] for f in pending_files]
    st.session_state.chat_messages.append(user_msg)

    st.session_state.pending_input = {
        "user_input": user_text,
        "pending_files": pending_files,
        "history": history,
    }
    st.rerun()
