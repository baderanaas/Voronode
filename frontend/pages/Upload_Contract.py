"""
Upload Contract Page

Upload contract PDFs for automated term extraction via Groq/Llama3.
"""

import streamlit as st
import sys
from pathlib import Path
import pandas as pd

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import format_file_size, format_currency

# Page config
st.set_page_config(
    page_title="Upload Contract - Voronode",
    page_icon="📑",
    layout="wide",
)

st.title("📑 Upload Contract")
st.markdown("Upload contract PDFs for automated term extraction and compliance integration.")

# Initialize API client
api = APIClient()

# File uploader
st.markdown("### Select Contract PDF")
uploaded_file = st.file_uploader(
    "Choose a PDF file",
    type=["pdf"],
    help="Upload a construction contract in PDF format",
)

if uploaded_file is not None:
    # Display file info
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Filename", uploaded_file.name)

    with col2:
        st.metric("Size", format_file_size(uploaded_file.size))

    with col3:
        st.metric("Type", uploaded_file.type)

    # Process button
    if st.button("📑 Extract Contract Terms", type="primary", use_container_width=True):
        with st.spinner("Extracting contract terms with Groq/Llama3..."):
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                status_text.text("Uploading file...")
                progress_bar.progress(10)

                file_content = uploaded_file.getvalue()

                status_text.text("Extracting text and structuring with LLM...")
                progress_bar.progress(30)

                result = api.upload_contract_stream(file_content, uploaded_file.name)

                progress_bar.progress(100)
                status_text.text("Extraction complete!")

                # Display results
                st.markdown("---")

                if result.get("success"):
                    st.success(f"Contract {result.get('contract_id', 'N/A')} extracted successfully!")

                    # Contract details
                    st.markdown("### Extracted Contract Data")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.metric("Contract ID", result.get("contract_id", "N/A"))
                        st.metric("Contractor", result.get("contractor_name", "N/A"))
                        st.metric("Project", result.get("project_name", "N/A"))

                    with col2:
                        st.metric("Contract Value", format_currency(result.get("value", 0)))
                        retention = result.get("retention_rate", 0)
                        if retention:
                            st.metric("Retention Rate", f"{float(retention) * 100:.0f}%")
                        st.metric("Period", f"{result.get('start_date', 'N/A')} to {result.get('end_date', 'N/A')}")

                    # Approved Cost Codes
                    codes = result.get("approved_cost_codes", [])
                    if codes:
                        st.markdown("### Approved Cost Codes")
                        st.write(", ".join(f"`{c}`" for c in codes))

                    # Unit Price Schedule
                    schedule = result.get("unit_price_schedule", {})
                    if schedule:
                        st.markdown("### Unit Price Schedule")
                        df = pd.DataFrame(
                            [{"Cost Code": k, "Max Unit Price": f"${v:,.2f}"} for k, v in schedule.items()]
                        )
                        st.dataframe(df, use_container_width=True, hide_index=True)

                    # Warnings
                    warnings = result.get("extraction_warnings", [])
                    if warnings:
                        st.markdown("### Extraction Warnings")
                        for w in warnings:
                            st.warning(w)

                    # Processing time
                    proc_time = result.get("processing_time_seconds")
                    if proc_time:
                        st.caption(f"Processed in {proc_time:.1f}s")

                else:
                    st.error(f"Extraction failed: {result.get('message', 'Unknown error')}")

            except Exception as e:
                progress_bar.progress(0)
                status_text.text("")
                st.error(f"Error processing contract: {e}")
                st.info("Make sure the FastAPI backend is running on http://localhost:8080")

else:
    st.info("Upload a contract PDF to extract terms automatically")

    st.markdown("### What gets extracted?")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("""
        **Contract Terms:**
        - Contract ID and parties
        - Contract value and dates
        - Retention rate
        - General terms summary
        """)

    with col2:
        st.markdown("""
        **Compliance Data:**
        - Approved cost codes
        - Unit price schedule
        - Billing cap (contract value)
        - Stored in Neo4j for auditing
        """)

# Sidebar
with st.sidebar:
    st.markdown("### How it works")
    st.markdown("""
    1. PDF text is extracted from the document
    2. Groq/Llama3 identifies contract terms
    3. Terms are validated for consistency
    4. Contract is stored in the knowledge graph
    5. Compliance auditor can now use these terms
    """)
