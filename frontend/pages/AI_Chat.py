"""
AI Chat Assistant Page

Conversational interface for querying invoices, contracts, budgets, and project data
using natural language powered by the multi-agent system.
"""

import streamlit as st
import sys
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# Add paths
frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient

# Page config
st.set_page_config(
    page_title="AI Assistant - Voronode",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 AI Assistant")
st.markdown("Ask questions about your invoices, contracts, budgets, and projects in natural language.")

# Initialize API client
api = APIClient()

# Initialize session state for conversation history
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

# Sidebar with examples and controls
with st.sidebar:
    st.markdown("### 💡 Example Questions")

    examples = [
        "Show me all invoices over $50,000",
        "Which contractor has the most violations?",
        "What's the budget variance for Project Alpha?",
        "Find overdue invoices",
        "Calculate total retention across all contracts",
        "Show me the top 5 most expensive invoices",
        "Which projects are over budget?",
        "Get contract details for ABC Contractors",
    ]

    for example in examples:
        if st.button(f"📝 {example}", key=example, use_container_width=True):
            # Add example to chat input
            st.session_state.example_query = example

    st.markdown("---")

    # Clear conversation
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.chat_messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("### ℹ️ How It Works")
    st.markdown("""
    The AI assistant uses a multi-agent system:

    1. **Planner** - Analyzes your query
    2. **Executor** - Runs tools (database queries, calculations)
    3. **Validator** - Checks response quality
    4. **Responder** - Formats the answer

    It can:
    - Query graph database (Neo4j)
    - Search documents (ChromaDB)
    - Run calculations
    - Check compliance
    - Search the web for context
    """)

# Display chat messages
for message in st.session_state.chat_messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

        # Display structured data if available
        if "display_data" in message and message["display_data"]:
            display_data = message["display_data"]
            display_format = message.get("display_format", "text")

            # Render table
            if display_format == "table" and "rows" in display_data:
                st.markdown("---")
                df = pd.DataFrame(display_data["rows"])
                st.dataframe(df, use_container_width=True)

                # Add summary if available
                if "summary" in display_data:
                    st.info(f"📊 {display_data['summary']}")

            # Render chart
            elif display_format == "chart":
                st.markdown("---")
                chart_type = display_data.get("chart_type", "bar")

                if chart_type == "bar":
                    fig = px.bar(
                        x=display_data.get("x_axis", []),
                        y=display_data.get("y_axis", []),
                        labels={"x": "Category", "y": "Value"},
                    )
                    st.plotly_chart(fig, use_container_width=True)

                elif chart_type == "line":
                    fig = px.line(
                        x=display_data.get("x_axis", []),
                        y=display_data.get("y_axis", []),
                        labels={"x": "Time", "y": "Value"},
                    )
                    st.plotly_chart(fig, use_container_width=True)

                elif chart_type == "pie":
                    fig = px.pie(
                        values=display_data.get("y_axis", []),
                        names=display_data.get("labels", []),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                # Add summary if available
                if "summary" in display_data:
                    st.info(f"📊 {display_data['summary']}")

            # Show metadata if available
            if "metadata" in display_data:
                with st.expander("🔍 Execution Details"):
                    metadata = display_data["metadata"]
                    cols = st.columns(3)

                    if "execution_time" in metadata:
                        cols[0].metric("⏱️ Time", f"{metadata['execution_time']:.2f}s")

                    if "tools_used" in metadata:
                        cols[1].metric("🔧 Tools Used", len(metadata['tools_used']))

                    if "record_count" in metadata:
                        cols[2].metric("📝 Records", metadata['record_count'])

# Chat input
user_input = st.chat_input("Ask a question about your invoices, contracts, budgets, or projects...")

# Handle example query from sidebar
if "example_query" in st.session_state:
    user_input = st.session_state.example_query
    del st.session_state.example_query

# Process user input
if user_input:
    # Add user message to chat
    st.session_state.chat_messages.append({
        "role": "user",
        "content": user_input,
    })

    # Display user message
    with st.chat_message("user"):
        st.markdown(user_input)

    # Get AI response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                # Prepare conversation history for API
                history = [
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in st.session_state.chat_messages[:-1]  # Exclude current message
                ]

                # Call chat API
                response = api.chat(
                    message=user_input,
                    conversation_history=history,
                    session_id=st.session_state.session_id,
                )

                # Extract response data
                response_text = response.get("response", "")
                display_format = response.get("display_format", "text")
                display_data = response.get("display_data")
                metadata = response.get("metadata", {})

                # Display response text
                st.markdown(response_text)

                # Display structured data if available
                if display_data:
                    # Render table
                    if display_format == "table" and "rows" in display_data:
                        st.markdown("---")
                        df = pd.DataFrame(display_data["rows"])
                        st.dataframe(df, use_container_width=True)

                        # Add summary if available
                        if "summary" in display_data:
                            st.info(f"📊 {display_data['summary']}")

                    # Render chart
                    elif display_format == "chart":
                        st.markdown("---")
                        chart_type = display_data.get("chart_type", "bar")

                        if chart_type == "bar":
                            fig = px.bar(
                                x=display_data.get("x_axis", []),
                                y=display_data.get("y_axis", []),
                                labels={"x": "Category", "y": "Value"},
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        elif chart_type == "line":
                            fig = px.line(
                                x=display_data.get("x_axis", []),
                                y=display_data.get("y_axis", []),
                                labels={"x": "Time", "y": "Value"},
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        elif chart_type == "pie":
                            fig = px.pie(
                                values=display_data.get("y_axis", []),
                                names=display_data.get("labels", []),
                            )
                            st.plotly_chart(fig, use_container_width=True)

                        # Add summary if available
                        if "summary" in display_data:
                            st.info(f"📊 {display_data['summary']}")

                    # Show metadata if available
                    if "metadata" in display_data:
                        with st.expander("🔍 Execution Details"):
                            metadata_data = display_data["metadata"]
                            cols = st.columns(3)

                            if "execution_time" in metadata_data:
                                cols[0].metric("⏱️ Time", f"{metadata_data['execution_time']:.2f}s")

                            if "tools_used" in metadata_data:
                                cols[1].metric("🔧 Tools Used", len(metadata_data['tools_used']))

                            if "record_count" in metadata_data:
                                cols[2].metric("📝 Records", metadata_data['record_count'])

                # Add assistant message to chat history
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": response_text,
                    "display_format": display_format,
                    "display_data": display_data,
                })

                # Show processing time
                if "processing_time_seconds" in metadata:
                    st.caption(f"⏱️ Processed in {metadata['processing_time_seconds']:.2f}s")

            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.error("Make sure the FastAPI backend is running and the multi-agent system is properly configured.")

                # Add error to chat history
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"Sorry, I encountered an error: {str(e)}",
                })

# Welcome message if no messages
if len(st.session_state.chat_messages) == 0:
    with st.chat_message("assistant"):
        st.markdown("""
        👋 **Welcome! I'm your AI assistant for financial risk management.**

        I can help you with:
        - 📊 Querying invoices, contracts, and budgets
        - 🔍 Finding compliance violations
        - 💰 Calculating financial metrics
        - 📈 Analyzing trends and variances
        - ⚠️ Identifying risks

        Try asking me a question or click an example from the sidebar!
        """)
