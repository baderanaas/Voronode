"""
Voronode — AI Assistant (main page)

Unified chat + document upload interface. This is the default page
that opens when the app starts.
"""

import streamlit as st
import streamlit.components.v1 as components
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
    ("pending_files", []),       # list of {"bytes": b"...", "name": "file.pdf"}
    ("uploader_key", 0),
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
            fig = px.bar(x=display_data.get("x_axis", []), y=display_data.get("y_axis", []))
            st.plotly_chart(fig, use_container_width=True)
        elif chart_type == "line":
            fig = px.line(x=display_data.get("x_axis", []), y=display_data.get("y_axis", []))
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


def clear_pending():
    st.session_state.pending_files = []
    st.session_state.uploader_key += 1  # reset file_uploader widget


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
        clear_pending()
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ How it works")
    st.markdown("""
    **Planner** → routes your query
    **Executor** → queries Neo4j, ChromaDB, compliance
    **Validator** → checks answer quality
    **Responder** → formats the result

    Upload a document to ingest it into the graph,
    then ask questions about it in the same thread.
    """)


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

# ── Welcome message (shown only on empty chat) ────────────────────────────────
if not st.session_state.chat_messages:
    with st.chat_message("assistant"):
        st.markdown("""
        👋 **Welcome — I'm your financial risk management assistant.**

        I can help you:
        - 📊 Query invoices, contracts, budgets, and projects
        - 🔍 Detect compliance violations and anomalies
        - 💰 Calculate financial metrics and variances
        - ⚠️ Identify risks across your project portfolio

        **Attach a document** below to ingest it, or just ask a question.
        """)

# ── Styles: bottom bar + full-page drop overlay ──────────────────────────────
st.markdown(
    """
    <style>
    /* ── Bottom bar: file uploader + form ── */
    /* Extra bottom padding so messages don't hide behind the bar */
    .main .block-container { padding-bottom: 10rem !important; }

    /* Compact file uploader — keep it visible but slim */
    [data-testid="stFileUploader"] > label { display: none !important; }
    [data-testid="stFileUploader"] { margin-bottom: 0.4rem !important; }
    section[data-testid="stFileUploaderDropzone"] {
        padding    : 0.5rem 1rem !important;
        border     : 1px dashed #4a4a5a !important;
    }
    /* Hide the native "filename X" row — our pending chip replaces it */
    [data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] {
        display: none !important;
    }

    /* ── Form: text input row ── */
    div[data-testid="stForm"] {
        border     : none !important;
        padding    : 0 !important;
        background : transparent !important;
    }
    div[data-testid="stForm"] [data-testid="stTextInput"] > label {
        display: none !important;
    }

    /* ── Pending-file chip ── */
    .pending-chip {
        display       : inline-flex;
        align-items   : center;
        gap           : 0.3rem;
        background    : #262730;
        border        : 1px solid #4a4a5a;
        border-radius : 1rem;
        padding       : 0.2rem 0.75rem;
        font-size     : 0.82rem;
        color         : #ccc;
        margin-bottom : 0.3rem;
    }
    .pending-chip b { color: #fafafa; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Full-page drag-and-drop JavaScript ───────────────────────────────────────
# Uses a guard so listeners are added only once (parent doc persists across reruns).
# Overlay is created in JS so it survives Streamlit reruns.
# On drop, files are forwarded to the hidden file-input inside the Streamlit uploader.
# NO dropzone expansion — avoids the invisible-overlay-blocks-page bug.
components.html(
    """
    <script>
    (function() {
        const pdoc = window.parent.document;

        // Guard: only attach listeners once
        if (pdoc._voronodeDragInit) return;
        pdoc._voronodeDragInit = true;

        // Create persistent overlay (survives Streamlit reruns)
        let overlay = pdoc.getElementById('vn-drop-overlay');
        if (!overlay) {
            overlay = pdoc.createElement('div');
            overlay.id = 'vn-drop-overlay';
            overlay.style.cssText =
                'display:none;position:fixed;inset:0;z-index:9998;'
              + 'background:rgba(14,17,23,0.88);justify-content:center;'
              + 'align-items:center;pointer-events:none;';
            overlay.innerHTML =
                '<div style="border:3px dashed #4a9eff;border-radius:1.5rem;'
              + 'padding:3rem 4rem;color:#4a9eff;font-size:1.3rem;font-weight:600;">'
              + 'Drop your document here</div>';
            pdoc.body.appendChild(overlay);
        }

        let dc = 0;

        pdoc.addEventListener('dragenter', e => {
            if (!e.dataTransfer || !e.dataTransfer.types.includes('Files')) return;
            e.preventDefault();
            dc++;
            overlay.style.display = 'flex';
        });

        pdoc.addEventListener('dragleave', e => {
            e.preventDefault();
            dc--;
            if (dc <= 0) { dc = 0; overlay.style.display = 'none'; }
        });

        pdoc.addEventListener('dragover', e => e.preventDefault());

        pdoc.addEventListener('drop', e => {
            e.preventDefault();
            dc = 0;
            overlay.style.display = 'none';

            if (!e.dataTransfer || !e.dataTransfer.files.length) return;

            // Forward dropped files to the Streamlit file-uploader input
            const input = pdoc.querySelector(
                'section[data-testid="stFileUploaderDropzone"] input[type="file"]'
            );
            if (input) {
                const dt = new DataTransfer();
                for (const f of e.dataTransfer.files) dt.items.add(f);
                input.files = dt.files;
                input.dispatchEvent(new Event('change', { bubbles: true }));
            }
        });
    })();
    </script>
    """,
    height=0,
)

# ── File uploader (multi-file, compact, receives drag-drop) ──────────────────
uploaded_files = st.file_uploader(
    "Attach",
    type=["pdf", "xlsx", "xls", "csv"],
    accept_multiple_files=True,
    key=f"file_attach_{st.session_state.uploader_key}",
    label_visibility="collapsed",
)
if uploaded_files:
    existing_names = {f["name"] for f in st.session_state.pending_files}
    for uf in uploaded_files:
        if uf.name not in existing_names:
            st.session_state.pending_files.append(
                {"bytes": uf.read(), "name": uf.name}
            )
    if len(st.session_state.pending_files) > len(existing_names):
        st.rerun()

# ── Pending file chips ───────────────────────────────────────────────────────
if st.session_state.pending_files:
    names = [f["name"] for f in st.session_state.pending_files]
    chip_html = " ".join(
        f"<span class='pending-chip'>📎 <b>{n}</b></span>" for n in names
    )
    chip_col, clear_col = st.columns([8, 0.5])
    chip_col.markdown(chip_html, unsafe_allow_html=True)
    if clear_col.button("✕", key="remove_pending"):
        clear_pending()
        st.rerun()

# ── Text input + Send (form for Enter-to-submit) ────────────────────────────
with st.form("chat_form", clear_on_submit=True, border=False):
    text_col, send_col = st.columns([10, 1])
    with text_col:
        n_files = len(st.session_state.pending_files)
        if n_files == 1:
            hint = f"Message — will include {st.session_state.pending_files[0]['name']}"
        elif n_files > 1:
            hint = f"Message — will include {n_files} files"
        else:
            hint = "Ask a question about invoices, contracts, budgets, or projects..."
        user_text = st.text_input(
            "Message",
            placeholder=hint,
            label_visibility="collapsed",
            key="chat_text",
        )
    with send_col:
        submitted = st.form_submit_button("↑")

# Allow submit with text, or with just pending files (no text)
has_pending = len(st.session_state.pending_files) > 0
user_input = user_text if submitted and user_text else None

# Sidebar example → chat input
if "example_query" in st.session_state:
    user_input = st.session_state.example_query
    del st.session_state.example_query


# ── Process submission ────────────────────────────────────────────────────────
if user_input or (submitted and has_pending):
    pending_files = list(st.session_state.pending_files)
    clear_pending()

    # Display the user turn (attachments + optional text)
    display_text = user_input or ""
    user_msg: dict = {"role": "user", "content": display_text}
    if pending_files:
        user_msg["attachments"] = [f["name"] for f in pending_files]
    st.session_state.chat_messages.append(user_msg)

    with st.chat_message("user"):
        if pending_files:
            names_html = " ".join(
                f"<span style='font-size:0.85rem;color:#888;'>📎 {f['name']}</span>"
                for f in pending_files
            )
            st.markdown(names_html, unsafe_allow_html=True)
        if display_text:
            st.markdown(display_text)

    with st.chat_message("assistant"):
        label = f"Processing {len(pending_files)} file(s)..." if pending_files else "Thinking..."
        with st.spinner(label):
            try:
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.chat_messages[:-1]
                    if m.get("content")
                ]
                response = api.send(
                    message=user_input or "",
                    files=pending_files or None,
                    conversation_history=history,
                    session_id=st.session_state.session_id,
                )

                response_text = response.get("response", "")
                display_format = response.get("display_format", "text")
                display_data = response.get("display_data")
                metadata = response.get("metadata", {})

                assistant_msg = {
                    "role": "assistant",
                    "content": response_text,
                    "display_format": display_format,
                    "display_data": display_data,
                }
                render_assistant_message(assistant_msg)
                st.session_state.chat_messages.append(assistant_msg)

                if "processing_time_seconds" in metadata:
                    st.caption(f"⏱️ {metadata['processing_time_seconds']:.2f}s")

            except Exception as e:
                err = f"Error: {e}"
                st.error(err)
                st.session_state.chat_messages.append(
                    {"role": "assistant", "content": f"❌ {err}"}
                )

    st.rerun()
