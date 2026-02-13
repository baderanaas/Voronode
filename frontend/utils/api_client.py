"""
API Client for Voronode Backend

Centralized client for all FastAPI endpoints with error handling, caching, and retry logic.
"""

import requests
from typing import Dict, List, Optional, Any
import streamlit as st
from pathlib import Path
import time


class APIClient:
    """Client for interacting with Voronode FastAPI backend."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.timeout = 30

    def _request(
        self, method: str, endpoint: str, **kwargs
    ) -> requests.Response:
        """Make HTTP request with error handling."""
        url = f"{self.base_url}{endpoint}"
        kwargs.setdefault("timeout", self.timeout)

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.ConnectionError:
            st.error(f"❌ Cannot connect to backend at {self.base_url}")
            st.info("Make sure the FastAPI server is running: `uvicorn backend.main:app --reload`")
            raise
        except requests.exceptions.Timeout:
            st.error(f"⏱️ Request timed out after {self.timeout}s")
            raise
        except requests.exceptions.HTTPError as e:
            st.error(f"❌ API Error: {e.response.status_code} - {e.response.text}")
            raise

    # Health & Status
    def health_check(self) -> Dict[str, Any]:
        """Check API health status."""
        response = self._request("GET", "/api/health")
        return response.json()

    # Invoice Upload & Processing
    @st.cache_data(ttl=60)
    def upload_invoice(_self, file_path: Path) -> Dict[str, Any]:
        """Upload and process an invoice PDF using LangGraph workflow."""
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/pdf")}
            response = _self._request("POST", "/api/invoices/upload-graph", files=files)
        return response.json()

    def upload_invoice_stream(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Upload invoice from streamlit file uploader using LangGraph workflow."""
        files = {"file": (filename, file_content, "application/pdf")}
        response = self._request("POST", "/api/invoices/upload-graph", files=files)
        return response.json()

    # Workflow Management
    @st.cache_data(ttl=10)
    def list_workflows(_self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all workflows, optionally filtered by status."""
        params = {"status": status} if status else {}
        response = _self._request("GET", "/api/workflows", params=params)
        return response.json()

    @st.cache_data(ttl=10)
    def get_workflow(_self, workflow_id: str) -> Dict[str, Any]:
        """Get detailed workflow information."""
        response = _self._request("GET", f"/api/workflows/{workflow_id}")
        return response.json()

    @st.cache_data(ttl=10)
    def list_quarantined_workflows(_self) -> List[Dict[str, Any]]:
        """Get all workflows in quarantine."""
        response = _self._request("GET", "/api/workflows/quarantined")
        return response.json()

    def resume_workflow(
        self,
        workflow_id: str,
        action: str,
        corrections: Optional[Dict[str, Any]] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resume a quarantined workflow with human decision."""
        # Convert action to approved boolean
        approved = action == "approve"

        payload = {
            "approved": approved,
            "corrections": corrections or {},
            "notes": notes or "",
        }
        response = self._request(
            "POST", f"/api/workflows/{workflow_id}/resume", json=payload
        )
        return response.json()

    # Graph Queries
    @st.cache_data(ttl=300)
    def query_graph(_self, cypher_query: str) -> Dict[str, Any]:
        """Execute custom Cypher query on Neo4j."""
        response = _self._request(
            "POST", "/api/graph/query", json={"query": cypher_query}
        )
        return response.json()

    @st.cache_data(ttl=60)
    def get_graph_stats(_self) -> Dict[str, Any]:
        """Get graph database statistics."""
        response = _self._request("GET", "/api/graph/stats")
        return response.json()

    @st.cache_data(ttl=120)
    def get_project_graph(_self, project_id: str) -> Dict[str, Any]:
        """Get subgraph for a specific project."""
        response = _self._request("GET", f"/api/graph/project/{project_id}")
        return response.json()

    # Analytics
    @st.cache_data(ttl=60)
    def get_processing_metrics(_self) -> Dict[str, Any]:
        """Get invoice processing metrics and statistics."""
        response = _self._request("GET", "/api/analytics/metrics")
        return response.json()

    @st.cache_data(ttl=60)
    def get_anomaly_distribution(_self) -> Dict[str, Any]:
        """Get distribution of anomaly types."""
        response = _self._request("GET", "/api/analytics/anomalies")
        return response.json()

    @st.cache_data(ttl=60)
    def get_risk_trends(_self, days: int = 30) -> Dict[str, Any]:
        """Get risk trends over time."""
        response = _self._request("GET", f"/api/analytics/trends?days={days}")
        return response.json()

    # Invoice Data
    @st.cache_data(ttl=30)
    def get_invoice(_self, invoice_id: str) -> Dict[str, Any]:
        """Get invoice details by ID."""
        response = _self._request("GET", f"/api/invoices/{invoice_id}")
        return response.json()

    @st.cache_data(ttl=30)
    def list_invoices(_self, limit: int = 100) -> List[Dict[str, Any]]:
        """List recent invoices."""
        response = _self._request("GET", f"/api/invoices?limit={limit}")
        return response.json()

    # Contract Data
    def upload_contract_stream(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Upload contract PDF for extraction and storage."""
        files = {"file": (filename, file_content, "application/pdf")}
        response = self._request("POST", "/api/contracts/upload", files=files)
        return response.json()

    @st.cache_data(ttl=300)
    def get_contract(_self, contract_id: str) -> Dict[str, Any]:
        """Get contract details."""
        response = _self._request("GET", f"/api/contracts/{contract_id}")
        return response.json()

    # Budget Data
    def upload_budget_stream(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """Upload budget Excel/CSV for extraction and storage."""
        # Determine content type based on file extension
        if filename.endswith(".csv"):
            content_type = "text/csv"
        else:
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        files = {"file": (filename, file_content, content_type)}
        response = self._request("POST", "/api/budgets/upload", files=files)
        return response.json()

    @st.cache_data(ttl=300)
    def get_budget(_self, budget_id: str) -> Dict[str, Any]:
        """Get budget details."""
        response = _self._request("GET", f"/api/budgets/{budget_id}")
        return response.json()

    @st.cache_data(ttl=300)
    def get_project_budgets(_self, project_id: str) -> Dict[str, Any]:
        """Get all budgets for a project."""
        response = _self._request("GET", f"/api/budgets/project/{project_id}")
        return response.json()

    @st.cache_data(ttl=300)
    def get_budget_variance(_self, budget_id: str) -> Dict[str, Any]:
        """Get budget variance analysis."""
        response = _self._request("GET", f"/api/budgets/{budget_id}/variance")
        return response.json()

    # Phase 7: Conversational AI
    def chat(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat message to the conversational AI system.

        Args:
            message: User message
            conversation_history: List of previous messages with 'role' and 'content'
            session_id: Optional session ID for conversation persistence

        Returns:
            Chat response with formatted text, display format, and data
        """
        payload = {
            "message": message,
            "conversation_history": conversation_history or [],
            "session_id": session_id,
        }
        response = self._request("POST", "/api/chat", json=payload)
        return response.json()

    # Cache Management
    @staticmethod
    def clear_cache():
        """Clear all cached API responses."""
        st.cache_data.clear()
