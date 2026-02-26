"""Invoice validation agent - detects anomalies in extracted invoice data."""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Any
import re
import structlog

from backend.core.models import Invoice, LineItem
from backend.core.config import settings
from backend.services.llm_client import GroqClient

logger = structlog.get_logger()


class ValidationAnomaly:
    """Represents a validation anomaly/error."""

    def __init__(
        self,
        type: str,
        severity: str,
        message: str,
        field: str = None,
        line_item_id: str = None,
        expected: Any = None,
        actual: Any = None,
    ):
        self.type = type
        self.severity = severity
        self.message = message
        self.field = field
        self.line_item_id = line_item_id
        self.expected = expected
        self.actual = actual

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
            "line_item_id": self.line_item_id,
            "expected": self.expected,
            "actual": self.actual,
        }


class InvoiceValidator:
    """Validate extracted invoice data and detect anomalies."""

    def __init__(self):
        self.llm_client = GroqClient()

    def validate_invoice(self, invoice: Invoice) -> List[ValidationAnomaly]:
        """
        Run all validation checks on an invoice.

        Args:
            invoice: Extracted invoice to validate

        Returns:
            List of validation anomalies (empty if valid)
        """
        anomalies = []

        # Field validation
        anomalies.extend(self._validate_required_fields(invoice))
        anomalies.extend(self._validate_date_fields(invoice))
        anomalies.extend(self._validate_invoice_number(invoice))

        # Math validation
        anomalies.extend(self._validate_line_item_math(invoice))
        anomalies.extend(self._validate_total_amount(invoice))

        # Semantic validation (if enabled)
        if settings.enable_semantic_validation:
            anomalies.extend(self._validate_semantics(invoice))

        logger.info(
            "invoice_validation_complete",
            invoice_number=invoice.invoice_number,
            anomalies_found=len(anomalies),
            severity_high=sum(1 for a in anomalies if a.severity == "high"),
        )

        return anomalies

    def _validate_required_fields(self, invoice: Invoice) -> List[ValidationAnomaly]:
        """Check that required fields are present and non-empty."""
        anomalies = []

        required_fields = {
            "invoice_number": invoice.invoice_number,
            "date": invoice.date,
            "contractor_id": invoice.contractor_id,
            "amount": invoice.amount,
        }

        for field_name, field_value in required_fields.items():
            if not field_value or (isinstance(field_value, str) and not field_value.strip()):
                anomalies.append(
                    ValidationAnomaly(
                        type="missing_field",
                        severity="high",
                        message=f"Required field '{field_name}' is missing or empty",
                        field=field_name,
                    )
                )

        # Check line items exist
        if not invoice.line_items:
            anomalies.append(
                ValidationAnomaly(
                    type="missing_line_items",
                    severity="high",
                    message="Invoice has no line items",
                )
            )

        return anomalies

    def _validate_date_fields(self, invoice: Invoice) -> List[ValidationAnomaly]:
        """Validate date fields are logical."""
        anomalies = []

        # Date should not be in the future
        if invoice.date > date.today():
            anomalies.append(
                ValidationAnomaly(
                    type="future_date",
                    severity="medium",
                    message="Invoice date is in the future",
                    field="date",
                    expected="<= today",
                    actual=str(invoice.date),
                )
            )

        # Due date should be after invoice date
        if invoice.due_date and invoice.due_date < invoice.date:
            anomalies.append(
                ValidationAnomaly(
                    type="invalid_due_date",
                    severity="medium",
                    message="Due date is before invoice date",
                    field="due_date",
                    expected=f"> {invoice.date}",
                    actual=str(invoice.due_date),
                )
            )

        return anomalies

    def _validate_invoice_number(self, invoice: Invoice) -> List[ValidationAnomaly]:
        """Validate invoice number format."""
        anomalies = []

        # Check basic format (alphanumeric + hyphens)
        if not re.match(r"^[A-Z0-9-]+$", invoice.invoice_number):
            anomalies.append(
                ValidationAnomaly(
                    type="invalid_invoice_number",
                    severity="low",
                    message="Invoice number contains invalid characters",
                    field="invoice_number",
                    actual=invoice.invoice_number,
                )
            )

        return anomalies

    def _validate_line_item_math(self, invoice: Invoice) -> List[ValidationAnomaly]:
        """Validate line item arithmetic: quantity × unit_price = total."""
        anomalies = []

        for item in invoice.line_items:
            expected_total = item.quantity * item.unit_price

            # Use is_math_correct property
            if not item.is_math_correct:
                anomalies.append(
                    ValidationAnomaly(
                        type="math_error",
                        severity="high",
                        message=f"Line item total incorrect: {item.quantity} × {item.unit_price} ≠ {item.total}",
                        line_item_id=item.id,
                        expected=float(expected_total),
                        actual=float(item.total),
                    )
                )

        return anomalies

    def _validate_total_amount(self, invoice: Invoice) -> List[ValidationAnomaly]:
        """Validate invoice total equals sum of line items."""
        anomalies = []

        line_items_sum = sum(item.total for item in invoice.line_items)
        tolerance = Decimal("0.01")

        if abs(invoice.amount - line_items_sum) > tolerance:
            anomalies.append(
                ValidationAnomaly(
                    type="total_mismatch",
                    severity="high",
                    message=f"Invoice total does not match sum of line items",
                    field="amount",
                    expected=float(line_items_sum),
                    actual=float(invoice.amount),
                )
            )

        return anomalies

    def _validate_semantics(self, invoice: Invoice) -> List[ValidationAnomaly]:
        """Use LLM to validate semantic correctness of cost codes vs descriptions."""
        anomalies = []

        for item in invoice.line_items:
            # Skip if cost code or description is missing
            if not item.cost_code or not item.description:
                continue

            try:
                validation_result = self.llm_client.validate_semantic(
                    field="cost_code",
                    value=item.cost_code,
                    context={"description": item.description},
                )

                # If validation fails with high confidence, flag it
                if (
                    not validation_result.get("valid", True)
                    and validation_result.get("confidence", 0) > 0.7
                ):
                    anomalies.append(
                        ValidationAnomaly(
                            type="semantic_mismatch",
                            severity="medium",
                            message=validation_result.get(
                                "reason", "Cost code does not match description"
                            ),
                            line_item_id=item.id,
                            field="cost_code",
                            actual=f"{item.cost_code} / {item.description}",
                        )
                    )

            except Exception as e:
                logger.warning(
                    "semantic_validation_failed",
                    line_item_id=item.id,
                    error=str(e),
                )

        return anomalies
