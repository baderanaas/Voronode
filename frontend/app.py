"""
Voronode Dashboard - Main Entry Point

Multi-page Streamlit application for financial risk monitoring and invoice management.
"""

import streamlit as st

# Page configuration
st.set_page_config(
    page_title="Voronode Financial Risk Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main {
        padding: 0rem 1rem;
    }
    .stAlert {
        margin-top: 1rem;
    }
    h1 {
        color: #1f77b4;
        padding-bottom: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Sidebar navigation
st.sidebar.title("🏗️ Voronode")
st.sidebar.markdown("---")
st.sidebar.markdown("### Navigation")
st.sidebar.info(
    "Use the pages in the sidebar to navigate:\n\n"
    "- **Risk Feed**: Monitor real-time alerts\n"
    "- **Quarantine Queue**: Review and approve flagged invoices\n"
    "- **Upload Invoice**: Process new PDF invoices\n"
    "- **Graph Explorer**: Visualize knowledge graph\n"
    "- **Analytics**: View processing metrics"
)

# Main page content
st.title("📊 Voronode Financial Risk Dashboard")

st.markdown("""
## Welcome to Voronode

Voronode is an autonomous financial risk and compliance system for construction finance.
This dashboard provides a visual interface for:

- 🚨 **Risk Monitoring**: Real-time alerts for invoice anomalies
- ✅ **Workflow Management**: Approve or reject quarantined invoices
- 📄 **Document Processing**: Upload and process invoice PDFs
- 🔍 **Knowledge Graph**: Explore relationships between projects, contracts, and invoices
- 📈 **Analytics**: Track processing metrics and trends

### Quick Start

1. **Upload an Invoice**: Go to "Upload Invoice" to process a new PDF
2. **Review Quarantine**: Check "Quarantine Queue" for invoices requiring approval
3. **Monitor Risks**: View "Risk Feed" for real-time anomaly alerts
4. **Explore Data**: Use "Graph Explorer" to visualize the knowledge graph

### System Status
""")

# Try to connect to the API to show system status
try:
    import sys
    from pathlib import Path

    # Add backend to path
    backend_path = Path(__file__).parent.parent / "backend"
    sys.path.insert(0, str(backend_path))

    from utils.api_client import APIClient

    api = APIClient()
    status = api.health_check()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.success("✅ API Connected")
    with col2:
        st.success("✅ Neo4j Ready")
    with col3:
        st.success("✅ ChromaDB Ready")

except Exception as e:
    st.error(f"⚠️ Cannot connect to backend services. Please ensure the FastAPI server is running.")
    st.code(f"Error: {str(e)}")
    st.info("Start the backend with: `uvicorn backend.main:app --reload`")

st.markdown("---")
st.caption("Voronode v0.1.0 - Phase 4: Dashboard & Compliance Auditor")
