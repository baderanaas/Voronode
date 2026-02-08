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
