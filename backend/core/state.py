from typing import TypedDict, Optional, List, Dict, Any
from typing_extensions import Annotated


class WorkflowState(TypedDict):
    """State object passed between agents in LangGraph workflow"""

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
