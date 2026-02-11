"""API request/response schemas."""

from typing import List, Optional, Dict, Any
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel


class LineItemResponse(BaseModel):
    """Line item response schema."""

    id: str
    description: str
    cost_code: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class ValidationAnomalyResponse(BaseModel):
    """Validation anomaly response schema."""

    type: str
    severity: str
    message: str
    field: Optional[str] = None
    line_item_id: Optional[str] = None
    expected: Optional[Any] = None
    actual: Optional[Any] = None


class InvoiceUploadResponse(BaseModel):
    """Response for invoice upload endpoint."""

    success: bool
    message: str
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    amount: Optional[Decimal] = None
    line_items_count: Optional[int] = None
    validation_anomalies: List[ValidationAnomalyResponse] = []
    processing_time_seconds: Optional[float] = None
    # Phase 3 additions
    workflow_id: Optional[str] = None
    retry_count: Optional[int] = None
    risk_level: Optional[str] = None
    requires_review: Optional[bool] = None


class InvoiceDetailResponse(BaseModel):
    """Response for invoice detail endpoint."""

    id: str
    invoice_number: str
    date: date
    due_date: Optional[date] = None
    amount: Decimal
    status: str
    contractor_name: Optional[str] = None
    line_items: List[LineItemResponse]


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    services: Dict[str, bool]
    timestamp: datetime


# Phase 3: Workflow-related schemas

class WorkflowStatusResponse(BaseModel):
    """Workflow status response."""

    document_id: str
    status: str
    paused: bool
    risk_level: Optional[str] = None
    retry_count: int
    created_at: str
    updated_at: str
    state: Optional[Dict[str, Any]] = None


class QuarantinedWorkflowResponse(BaseModel):
    """Quarantined workflow response."""

    document_id: str
    status: str
    risk_level: Optional[str] = None
    retry_count: int
    pause_reason: Optional[str] = None
    anomalies: List[ValidationAnomalyResponse] = []
    created_at: str
    updated_at: str


class WorkflowResumeRequest(BaseModel):
    """Request to resume a quarantined workflow."""

    approved: bool
    corrections: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class ContractUploadResponse(BaseModel):
    """Response for contract upload endpoint."""

    success: bool
    message: str
    contract_id: Optional[str] = None
    contractor_name: Optional[str] = None
    project_name: Optional[str] = None
    value: Optional[Decimal] = None
    retention_rate: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    approved_cost_codes: List[str] = []
    unit_price_schedule: Dict[str, float] = {}
    extraction_warnings: List[str] = []
    processing_time_seconds: Optional[float] = None


class ContractDetailResponse(BaseModel):
    """Response for contract detail endpoint."""

    id: str
    contractor_id: Optional[str] = None
    contractor_name: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    value: Optional[float] = None
    retention_rate: Optional[float] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    terms: Optional[str] = None
    unit_price_schedule: Dict[str, float] = {}
    approved_cost_codes: List[str] = []
    extraction_confidence: Optional[float] = None


class BudgetLineResponse(BaseModel):
    """Response for a single budget line."""

    id: str
    cost_code: str
    description: str
    allocated: float
    spent: float
    remaining: float
    variance_percent: Optional[float] = None  # (spent - allocated) / allocated * 100


class BudgetUploadResponse(BaseModel):
    """Response for budget upload endpoint."""

    success: bool
    message: str
    budget_id: Optional[str] = None
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    total_allocated: Optional[float] = None
    total_spent: Optional[float] = None
    total_remaining: Optional[float] = None
    line_count: Optional[int] = None
    validation_warnings: List[str] = []
    processing_time_seconds: Optional[float] = None


class BudgetDetailResponse(BaseModel):
    """Response for budget detail endpoint."""

    id: str
    project_id: str
    project_name: Optional[str] = None
    total_allocated: float
    total_spent: float
    total_remaining: float
    line_count: int
    status: str
    budget_lines: List[BudgetLineResponse] = []


class BudgetVarianceResponse(BaseModel):
    """Response for budget variance analysis."""

    budget_id: str
    project_id: str
    project_name: Optional[str] = None
    overall_variance: float  # Total variance as percentage
    overall_variance_amount: float  # Dollar amount
    line_variances: List[Dict[str, Any]] = []  # Per cost code variance
    overrun_lines: List[str] = []  # Cost codes with overruns
    underrun_lines: List[str] = []  # Cost codes under budget
    at_risk_lines: List[str] = []  # Cost codes >90% spent
