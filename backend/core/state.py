from typing import TypedDict, Optional, List, Dict, Any
from typing_extensions import Annotated


class WorkflowState(TypedDict):
    """State object passed between agents in LangGraph workflow"""

    # User identity
    user_id: Optional[str]  # defaults to "default_user" until auth is added

    # Document info
    document_id: str
    document_path: str
    document_type: str  # invoice, contract, change_order

    # Processing data
    raw_text: Optional[str]
    extracted_data: Optional[Dict[str, Any]]

    # Validation & analysis
    validation_results: Annotated[List[Dict], lambda x, y: x + y]  # Append-only
    anomalies: Annotated[List[Dict], lambda x, y: x + y]  # Append-only

    # Agent feedback
    critic_feedback: Optional[str]
    retry_count: int
    max_retries: int

    # Graph updates
    graph_updated: bool

    # Risk assessment
    risk_level: str  # low, medium, high, critical
    final_report: Optional[Dict[str, Any]]

    # Workflow control (Phase 3 additions)
    status: str  # processing, quarantined, completed, failed
    paused: bool
    pause_reason: Optional[str]
    human_feedback: Optional[Dict]
    error_history: Annotated[List[Dict], lambda x, y: x + y]  # Append-only
    processing_time_ms: int
    neo4j_id: Optional[str]  # Neo4j invoice node ID
    extraction_confidence: Optional[float]
    current_node: Optional[str]  # Current node being executed
