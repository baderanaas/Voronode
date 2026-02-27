"""
Voronode — entry point.

Defines the navigation structure. All page-level set_page_config calls
have been removed; only this file calls it.
"""

import streamlit as st

st.set_page_config(
    page_title="Voronode",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not st.session_state.get("token"):
    pg = st.navigation(
        [st.Page("pages/Login.py", title="Login", icon="🔐")],
        position="hidden",
    )
else:
    pg = st.navigation(
        [
            st.Page("pages/Chat.py", title="Chat", icon="💬"),
            st.Page("pages/Analytics.py", title="Analytics", icon="📊"),
            st.Page("pages/Graph_Explorer.py", title="Graph Explorer", icon="🔍"),
            st.Page("pages/Quarantine_Queue.py", title="Quarantine Queue", icon="⚠️"),
            st.Page("pages/Risk_Feed.py", title="Risk Feed", icon="🚨"),
        ]
    )
pg.run()
