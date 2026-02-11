"""
Upload Budget Page

Upload budget Excel/CSV files for automated extraction and variance tracking.
"""

import streamlit as st
import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient
from utils.formatters import format_file_size, format_currency

# Page config
st.set_page_config(
    page_title="Upload Budget - Voronode",
    page_icon="💰",
    layout="wide",
)

st.title("💰 Upload Budget")
st.markdown("Upload budget Excel/CSV files for automated extraction and variance analysis.")

# Initialize API client
api = APIClient()

# File uploader
st.markdown("### Select Budget File")
uploaded_file = st.file_uploader(
    "Choose an Excel or CSV file",
    type=["xlsx", "xls", "csv"],
    help="Upload a project budget in Excel or CSV format with cost codes and allocations",
)

if uploaded_file is not None:
    # Display file info
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Filename", uploaded_file.name)

    with col2:
        st.metric("Size", format_file_size(uploaded_file.size))

    with col3:
        file_type = "Excel" if uploaded_file.name.endswith((".xlsx", ".xls")) else "CSV"
        st.metric("Type", file_type)

    # Preview file contents
    st.markdown("### File Preview")
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)

        # Reset file pointer after preview
        uploaded_file.seek(0)

        st.dataframe(df.head(10), use_container_width=True)
        st.caption(f"Showing first 10 rows of {len(df)} total rows")

    except Exception as e:
        st.error(f"Error previewing file: {e}")

    # Upload button
    st.markdown("### Process Budget")

    if st.button("🚀 Upload and Extract Budget", type="primary", use_container_width=True):
        with st.spinner("Processing budget file..."):
            try:
                # Reset file pointer
                uploaded_file.seek(0)

                # Upload via API
                response = api.upload_budget_stream(
                    file_content=uploaded_file.read(),
                    filename=uploaded_file.name,
                )

                if response.get("success"):
                    st.success("✅ Budget uploaded and processed successfully!")

                    # Display extraction results
                    st.markdown("### Budget Summary")

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        st.metric(
                            "Total Allocated",
                            format_currency(response.get("total_allocated", 0)),
                        )

                    with col2:
                        st.metric(
                            "Total Spent",
                            format_currency(response.get("total_spent", 0)),
                        )

                    with col3:
                        st.metric(
                            "Total Remaining",
                            format_currency(response.get("total_remaining", 0)),
                            delta=None,
                        )

                    with col4:
                        st.metric(
                            "Budget Lines",
                            response.get("line_count", 0),
                        )

                    # Project info
                    st.markdown("### Project Information")
                    proj_col1, proj_col2, proj_col3 = st.columns(3)

                    with proj_col1:
                        st.info(f"**Project ID:** {response.get('project_id', 'N/A')}")

                    with proj_col2:
                        st.info(f"**Project Name:** {response.get('project_name', 'N/A')}")

                    with proj_col3:
                        st.info(f"**Budget ID:** {response.get('budget_id', 'N/A')}")

                    # Warnings
                    if response.get("validation_warnings"):
                        st.warning("⚠️ Validation Warnings")
                        for warning in response["validation_warnings"]:
                            st.markdown(f"- {warning}")

                    # Processing time
                    st.caption(
                        f"Processed in {response.get('processing_time_seconds', 0):.2f} seconds"
                    )

                    # Fetch and display budget details
                    budget_id = response.get("budget_id")
                    if budget_id:
                        st.markdown("### Budget Lines")

                        with st.spinner("Loading budget details..."):
                            budget_details = api.get_budget(budget_id)

                            if budget_details and budget_details.get("budget_lines"):
                                # Convert to DataFrame
                                lines_data = []
                                for line in budget_details["budget_lines"]:
                                    lines_data.append({
                                        "Cost Code": line["cost_code"],
                                        "Description": line["description"],
                                        "Allocated": line["allocated"],
                                        "Spent": line["spent"],
                                        "Remaining": line["remaining"],
                                        "Variance %": line.get("variance_percent", 0),
                                    })

                                df_lines = pd.DataFrame(lines_data)

                                # Display table with formatting
                                st.dataframe(
                                    df_lines.style.format({
                                        "Allocated": "${:,.2f}",
                                        "Spent": "${:,.2f}",
                                        "Remaining": "${:,.2f}",
                                        "Variance %": "{:.2f}%",
                                    }),
                                    use_container_width=True,
                                )

                                # Visualization: Budget allocation by cost code
                                st.markdown("### Budget Allocation by Cost Code")

                                fig_allocation = px.bar(
                                    df_lines,
                                    x="Cost Code",
                                    y=["Allocated", "Spent", "Remaining"],
                                    title="Budget Allocation vs Spend",
                                    barmode="group",
                                    color_discrete_sequence=["#1f77b4", "#ff7f0e", "#2ca02c"],
                                )
                                fig_allocation.update_layout(
                                    xaxis_title="Cost Code",
                                    yaxis_title="Amount ($)",
                                    legend_title="Category",
                                )
                                st.plotly_chart(fig_allocation, use_container_width=True)

                                # Visualization: Variance heatmap
                                st.markdown("### Variance Analysis")

                                fig_variance = go.Figure(data=[
                                    go.Bar(
                                        x=df_lines["Cost Code"],
                                        y=df_lines["Variance %"],
                                        marker_color=df_lines["Variance %"].apply(
                                            lambda x: "#ff4b4b" if x > 10 else (
                                                "#ffa500" if x > 0 else "#00cc66"
                                            )
                                        ),
                                        text=df_lines["Variance %"].apply(lambda x: f"{x:.1f}%"),
                                        textposition="outside",
                                    )
                                ])

                                fig_variance.update_layout(
                                    title="Budget Variance by Cost Code",
                                    xaxis_title="Cost Code",
                                    yaxis_title="Variance (%)",
                                    showlegend=False,
                                )

                                # Add reference line at 0
                                fig_variance.add_hline(
                                    y=0,
                                    line_dash="dash",
                                    line_color="gray",
                                    annotation_text="On Budget",
                                )

                                st.plotly_chart(fig_variance, use_container_width=True)

                                # Get variance details
                                st.markdown("### Variance Summary")

                                variance_response = api.get_budget_variance(budget_id)

                                if variance_response:
                                    var_col1, var_col2, var_col3 = st.columns(3)

                                    with var_col1:
                                        overall_var = variance_response.get("overall_variance", 0)
                                        var_color = "🔴" if overall_var > 10 else "🟢"
                                        st.metric(
                                            "Overall Variance",
                                            f"{overall_var:.2f}%",
                                            delta=format_currency(
                                                variance_response.get("overall_variance_amount", 0)
                                            ),
                                        )

                                    with var_col2:
                                        overrun_count = len(variance_response.get("overrun_lines", []))
                                        st.metric("Overrun Lines", overrun_count)

                                    with var_col3:
                                        at_risk_count = len(variance_response.get("at_risk_lines", []))
                                        st.metric("At Risk Lines (>90%)", at_risk_count)

                                    # Alert for overruns
                                    if variance_response.get("overrun_lines"):
                                        st.error("⚠️ **Budget Overruns Detected**")
                                        st.markdown("**Cost codes over budget:**")
                                        for code in variance_response["overrun_lines"]:
                                            st.markdown(f"- `{code}`")

                                    # Warning for at-risk
                                    if variance_response.get("at_risk_lines"):
                                        st.warning("⚠️ **At-Risk Budget Lines**")
                                        st.markdown("**Cost codes >90% utilized:**")
                                        for code in variance_response["at_risk_lines"]:
                                            st.markdown(f"- `{code}`")

                else:
                    st.error(f"❌ Upload failed: {response.get('message', 'Unknown error')}")

            except Exception as e:
                st.error(f"❌ Error uploading budget: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

else:
    # Instructions
    st.info("""
    **Budget File Requirements:**

    - Supported formats: Excel (.xlsx, .xls) or CSV (.csv)
    - Required columns:
        - **Cost Code** (or Code, Account Code)
        - **Budget** (or Allocated, Amount)
        - **Description** (or Item, Line Item) - optional
        - **Spent** (or Actual, Expended) - optional
        - **Remaining** (or Balance, Available) - optional

    The system will automatically:
    - Extract project information
    - Parse budget line items
    - Calculate variances
    - Detect overruns and at-risk lines
    """)

    # Sample data format
    st.markdown("### Sample Budget Format")

    sample_data = pd.DataFrame({
        "Cost Code": ["01-100", "05-500", "15-100", "16-100"],
        "Description": ["Site Preparation", "Structural Steel", "Plumbing", "Electrical"],
        "Budget": [400000, 800000, 350000, 600000],
        "Spent": [145000, 310000, 88000, 420000],
        "Remaining": [255000, 490000, 262000, 180000],
    })

    st.dataframe(sample_data, use_container_width=True)
