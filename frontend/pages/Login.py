"""
Voronode — Login / Register page

Standalone auth page. On successful login or registration the token is
stored in st.session_state and the user is redirected to Chat.
"""

import sys
from pathlib import Path

import streamlit as st

frontend_path = Path(__file__).parent.parent
sys.path.insert(0, str(frontend_path))

from utils.api_client import APIClient

# Shared api client (no token yet)
if "api" not in st.session_state:
    st.session_state.api = APIClient()

api: APIClient = st.session_state.api

# Already logged in — go straight to chat (triggers app.py to rerun with full nav)
if st.session_state.get("token"):
    st.rerun()

st.title("Voronode")
st.subheader("Financial Risk & Compliance Assistant")
st.markdown("---")

tab_login, tab_register = st.tabs(["Login", "Register"])

with tab_login:
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Please enter both username and password.")
        else:
            try:
                token = api.login(username, password)
                st.session_state.token = token
                st.session_state.username = username
                # Clear any stale conversation state
                st.session_state.pop("chat_messages", None)
                st.session_state.pop("current_conversation_id", None)
                st.session_state.pop("conversations", None)
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

with tab_register:
    with st.form("register_form"):
        new_username = st.text_input("Username", key="reg_username")
        new_password = st.text_input("Password", type="password", key="reg_password")
        confirm_password = st.text_input("Confirm password", type="password", key="reg_confirm")
        reg_submitted = st.form_submit_button("Create account", use_container_width=True)

    if reg_submitted:
        if not new_username or not new_password:
            st.error("Please fill in all fields.")
        elif len(new_username) < 3:
            st.error("Username must be at least 3 characters.")
        elif len(new_password) < 8:
            st.error("Password must be at least 8 characters.")
        elif new_password != confirm_password:
            st.error("Passwords do not match.")
        else:
            try:
                token = api.register(new_username, new_password)
                st.session_state.token = token
                st.session_state.username = new_username
                # Clear any stale conversation state
                st.session_state.pop("chat_messages", None)
                st.session_state.pop("current_conversation_id", None)
                st.session_state.pop("conversations", None)
                st.rerun()
            except Exception as e:
                st.error(f"Registration failed: {e}")
