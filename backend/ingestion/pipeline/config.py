"""Workflow configuration settings."""

from pydantic import BaseModel
from typing import Dict, Any


class WorkflowConfig(BaseModel):
    """Configuration for invoice processing workflow."""

    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: int = 1

    # Risk thresholds
    quarantine_on_high_risk: bool = True
    quarantine_on_critical_risk: bool = True

    # Checkpointing
    enable_checkpointing: bool = True
    checkpoint_db_path: str = "workflow_checkpoints.db"

    # State persistence
    state_db_path: str = "workflow_states.db"

    # Timeout settings (seconds)
    extraction_timeout: int = 30
    validation_timeout: int = 10
    graph_insertion_timeout: int = 15

    # Feature flags
    enable_critic_agent: bool = True
    enable_vector_embedding: bool = True
    enable_semantic_validation: bool = True


# Default configuration
DEFAULT_WORKFLOW_CONFIG = WorkflowConfig()
