from __future__ import annotations

import uuid
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime
from decimal import Decimal


class LineItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    description: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal
    cost_code: str

    @property
    def is_math_correct(self) -> bool:
        """Check if quantity × unit_price = total (within 1 cent tolerance)"""
        expected = self.quantity * self.unit_price
        return abs(expected - self.total) < Decimal("0.01")


class Invoice(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    invoice_number: str
    date: date
    due_date: Optional[date] = None
    contractor_id: str  # Can be name if ID unknown
    contract_id: Optional[str] = None  # Make optional for extraction
    amount: Decimal
    status: str = "pending"  # pending, approved, paid, rejected
    line_items: List[LineItem] = []

    # Extraction tracking
    extracted_at: Optional[datetime] = None
    extraction_confidence: Optional[float] = None


class Contract(BaseModel):
    id: str
    contractor_id: str
    project_id: str
    value: Decimal
    retention_rate: Decimal = Field(ge=0, le=1)  # e.g., 0.10 for 10%
    start_date: date
    end_date: date
    terms: str


class Project(BaseModel):
    id: str
    name: str
    budget: Decimal
    start_date: date
    end_date: date
    status: str = "active"  # active, completed, on_hold


class Contractor(BaseModel):
    id: str
    name: str
    license_number: str
    rating: Optional[float] = Field(None, ge=0, le=5)


class BudgetLine(BaseModel):
    id: str
    project_id: str
    cost_code: str
    description: str
    allocated: Decimal
    spent: Decimal = Decimal(0)
    remaining: Decimal


class RiskFactor(BaseModel):
    id: str
    type: str  # budget_overrun, payment_delay, compliance_violation
    severity: str  # low, medium, high, critical
    description: str
    detected_date: datetime
    status: str = "active"  # active, resolved, false_positive
