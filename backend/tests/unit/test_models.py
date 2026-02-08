from backend.core.models import Invoice, LineItem, Contract
from decimal import Decimal
from datetime import date


def test_invoice_creation():
    """Test Invoice model validation"""
    line_item = LineItem(
        id="li1",
        description="Concrete pour",
        quantity=Decimal("100"),
        unit_price=Decimal("50.00"),
        total=Decimal("5000.00"),
        cost_code="03-300"
    )

    invoice = Invoice(
        id="inv1",
        invoice_number="INV-001",
        date=date(2024, 1, 15),
        contractor_id="con1",
        contract_id="contract1",
        amount=Decimal("5000.00"),
        line_items=[line_item]
    )

    assert invoice.invoice_number == "INV-001"
    assert len(invoice.line_items) == 1
    assert invoice.status == "pending"


def test_contract_retention_rate_validation():
    """Test Contract retention rate constraints"""
    contract = Contract(
        id="c1",
        contractor_id="con1",
        project_id="p1",
        value=Decimal("100000"),
        retention_rate=Decimal("0.10"),
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        terms="Standard terms"
    )

    assert contract.retention_rate == Decimal("0.10")
