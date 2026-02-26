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
    ("pending_bytes", None),
    ("pending_name", None),
    ("pending_doc_type", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helpers ───────────────────────────────────────────────────────────────────
DOC_ICONS = {"invoice": "🧾", "contract": "📄", "budget": "📊"}


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


def render_upload_result(result: dict, doc_type: str):
    """Show extracted document data inline after upload."""
    if doc_type == "invoice":
        data = result.get("extracted_data", {})
        status = result.get("status", "unknown")
        risk = result.get("risk_level", "unknown")
        anomalies = result.get("anomalies", [])

        icon = "✅" if status == "completed" else "⚠️" if status == "quarantined" else "🔄"
        st.markdown(f"{icon} **Invoice processed** — status: `{status}` | risk: `{risk}`")

        if data:
            c1, c2, c3 = st.columns(3)
            c1.metric("Invoice #", data.get("invoice_number", "—"))
            c2.metric("Amount", f"${float(data.get('total_amount', 0)):,.2f}")
            c3.metric("Contractor", data.get("contractor_name", "—"))

        if anomalies:
            st.warning(f"⚠️ {len(anomalies)} anomaly(s) detected")
            for a in anomalies[:3]:
                a = a if isinstance(a, dict) else {}
                st.caption(
                    f"• **{a.get('type', 'unknown')}** [{a.get('severity', '')}]: "
                    f"{a.get('message', '')}"
                )

    elif doc_type == "contract":
        data = result.get("contract", {})
        if data:
            c1, c2, c3 = st.columns(3)
            c1.metric("Contract #", data.get("contract_id", "—"))
            c2.metric("Value", f"${float(data.get('contract_value', 0)):,.2f}")
            c3.metric("Retention", f"{float(data.get('retention_rate', 0)) * 100:.1f}%")
        warnings = result.get("warnings", [])
        if warnings:
            st.warning(f"⚠️ {len(warnings)} warning(s): {'; '.join(warnings[:2])}")
        else:
            st.success("✅ Contract extracted successfully")

    elif doc_type == "budget":
        data = result.get("budget", {})
        if data:
            c1, c2, c3 = st.columns(3)
            c1.metric("Project", data.get("project_id", "—"))
            c2.metric("Allocated", f"${float(data.get('total_allocated', 0)):,.2f}")
            c3.metric("Lines", len(data.get("budget_lines", [])))
        st.success("✅ Budget loaded successfully")


def process_upload(bytes_data: bytes, name: str, doc_type: str) -> tuple[str, dict]:
    """Upload document via /chat/upload and return (summary_text, result_dict)."""
    result = api.upload_document(bytes_data, name, message=f"Process this {doc_type}")
    response_text = result.get("response", "")
    summary = f"Processed **{name}** ({doc_type})"
    return summary, result


def clear_pending():
    st.session_state.pending_bytes = None
    st.session_state.pending_name = None
    st.session_state.pending_doc_type = None


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
            attachment = msg.get("attachment")
            if attachment:
                icon = DOC_ICONS.get(attachment["type"], "📎")
                st.markdown(
                    f"<span style='font-size:0.85rem;color:#888;'>"
                    f"{icon} {attachment['name']}</span>",
                    unsafe_allow_html=True,
                )
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

# ── File uploader (compact, always visible, receives drag-drop) ──────────────
uploaded = st.file_uploader(
    "Attach",
    type=["pdf", "xlsx", "xls", "csv"],
    key="file_attach",
    label_visibility="collapsed",
)
if uploaded is not None and st.session_state.pending_name != uploaded.name:
    ext = Path(uploaded.name).suffix.lower()
    st.session_state.pending_bytes = uploaded.read()
    st.session_state.pending_name = uploaded.name
    st.session_state.pending_doc_type = (
        "budget" if ext in (".xlsx", ".xls", ".csv") else "invoice"
    )
    st.rerun()

# ── Pending file chip + type selector ────────────────────────────────────────
if st.session_state.pending_bytes:
    icon = DOC_ICONS.get(st.session_state.pending_doc_type, "📎")
    ext = Path(st.session_state.pending_name).suffix.lower()
    if ext == ".pdf":
        chip_col, type_col, clear_col = st.columns([6, 2, 0.5])
    else:
        chip_col, clear_col = st.columns([8, 0.5])
    chip_col.markdown(
        f"<div class='pending-chip'>{icon} <b>{st.session_state.pending_name}</b></div>",
        unsafe_allow_html=True,
    )
    if ext == ".pdf":
        def _on_type_change():
            st.session_state.pending_doc_type = st.session_state._type_select

        type_col.selectbox(
            "Type",
            ["invoice", "contract"],
            index=["invoice", "contract"].index(st.session_state.pending_doc_type),
            key="_type_select",
            label_visibility="collapsed",
            on_change=_on_type_change,
        )
    if clear_col.button("✕", key="remove_pending"):
        clear_pending()
        st.rerun()

# ── Text input + Send (form for Enter-to-submit) ────────────────────────────
with st.form("chat_form", clear_on_submit=True, border=False):
    text_col, send_col = st.columns([10, 1])
    with text_col:
        placeholder = (
            f"Message — will include {st.session_state.pending_name}"
            if st.session_state.pending_bytes is not None
            else "Ask a question about invoices, contracts, budgets, or projects..."
        )
        user_text = st.text_input(
            "Message",
            placeholder=placeholder,
            label_visibility="collapsed",
            key="chat_text",
        )
    with send_col:
        submitted = st.form_submit_button("↑")

user_input = user_text if submitted and user_text else None

# Sidebar example → chat input
if "example_query" in st.session_state:
    user_input = st.session_state.example_query
    del st.session_state.example_query


# ── Process submission ────────────────────────────────────────────────────────
if user_input:
    pending_bytes = st.session_state.pending_bytes
    pending_name = st.session_state.pending_name
    pending_doc_type = st.session_state.pending_doc_type
    clear_pending()

    user_msg: dict = {"role": "user", "content": user_input}
    if pending_bytes:
        user_msg["attachment"] = {"name": pending_name, "type": pending_doc_type}
    st.session_state.chat_messages.append(user_msg)

    with st.chat_message("user"):
        if pending_bytes:
            icon = DOC_ICONS.get(pending_doc_type, "📎")
            st.markdown(
                f"<span style='font-size:0.85rem;color:#888;'>"
                f"{icon} {pending_name}</span>",
                unsafe_allow_html=True,
            )
        st.markdown(user_input)

    # Step 1: upload file if attached
    upload_context = ""
    if pending_bytes:
        with st.chat_message("assistant"):
            with st.spinner(f"Processing {pending_name}..."):
                try:
                    upload_resp = api.upload_document(pending_bytes, pending_name)
                    upload_text = upload_resp.get("response", "File processed.")
                    st.markdown(upload_text)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": upload_text}
                    )
                    # Save context so the chat question knows which document.
                    # Include the full result so the planner can extract
                    # identifiers (invoice_number, contract_id, etc.)
                    # and query Neo4j by the correct property.
                    upload_context = (
                        f"[Context: the user just uploaded '{pending_name}'. "
                        f"Processing result: {upload_text} "
                        f"To query this document in Neo4j, use its ID or "
                        f"number (e.g. invoice_number), NOT the filename.]\n\n"
                    )
                except Exception as e:
                    err = f"Failed to process {pending_name}: {e}"
                    st.error(err)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": f"❌ {err}"}
                    )

    # Step 2: send the user's text question through chat
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                history = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.chat_messages[:-1]
                    if m.get("content")
                ]
                chat_message = f"{upload_context}{user_input}"
                response = api.chat(
                    message=chat_message,
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
