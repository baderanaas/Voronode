"""
Contract Compliance Auditor Agent

Validates invoices against contract terms to detect:
- Retention rate violations
- Unit price mismatches
- Billing cap violations
- Out-of-scope charges
"""

import structlog
from typing import List, Optional, Dict, Any
from decimal import Decimal
from datetime import datetime

from backend.core.models import Invoice, Contract, ComplianceAnomaly, ContractTerm, LineItem
from backend.graph.client import Neo4jClient

logger = structlog.get_logger()


class ContractComplianceAuditor:
    """
    Audits invoices for compliance with contract terms.

    This agent validates invoices against their associated contracts,
    checking for violations in retention rates, unit prices, billing caps,
    and scope (approved cost codes).
    """

    def __init__(self, neo4j_client: Neo4jClient):
        self.neo4j = neo4j_client

    def audit_invoice(self, invoice: Invoice) -> List[ComplianceAnomaly]:
        """
        Perform comprehensive compliance audit on an invoice.

        Args:
            invoice: Invoice to audit

        Returns:
            List of compliance anomalies detected
        """
        logger.info(
            "Starting compliance audit",
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            contract_id=invoice.contract_id,
        )

        anomalies = []

        # Must have a contract ID to audit
        if not invoice.contract_id:
            logger.warning("Cannot audit invoice without contract_id", invoice_id=invoice.id)
            anomalies.append(
                ComplianceAnomaly(
                    type="missing_contract",
                    severity="high",
                    message="Invoice has no associated contract for compliance validation",
                    contract_id="UNKNOWN",
                    invoice_id=invoice.id,
                )
            )
            return anomalies

        # Fetch contract from Neo4j
        contract = self._get_contract_from_neo4j(invoice.contract_id)

        if not contract:
            logger.error("Contract not found in database", contract_id=invoice.contract_id)
            anomalies.append(
                ComplianceAnomaly(
                    type="contract_not_found",
                    severity="critical",
                    message=f"Contract {invoice.contract_id} not found in knowledge graph",
                    contract_id=invoice.contract_id,
                    invoice_id=invoice.id,
                )
            )
            return anomalies

        # Get contract terms
        contract_terms = self._extract_contract_terms(contract)

        # Run validation checks
        anomalies.extend(self._validate_retention(invoice, contract_terms))
        anomalies.extend(self._validate_unit_prices(invoice, contract_terms))
        anomalies.extend(self._validate_billing_cap(invoice, contract, contract_terms))
        anomalies.extend(self._validate_scope(invoice, contract_terms))

        logger.info(
            "Compliance audit completed",
            invoice_id=invoice.id,
            anomalies_found=len(anomalies),
        )

        return anomalies

    def _get_contract_from_neo4j(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Fetch contract from Neo4j knowledge graph."""
        query = """
        MATCH (c:Contract {contract_id: $contract_id})
        RETURN c
        """

        with self.neo4j.driver.session() as session:
            result = session.run(query, contract_id=contract_id)
            record = result.single()

            if record:
                return dict(record["c"])

        return None

    def _extract_contract_terms(self, contract: Dict[str, Any]) -> ContractTerm:
        """
        Extract contract terms from Neo4j contract node.

        In a real system, these would be stored in the contract.
        For now, we'll use defaults and what's available.
        """
        retention_rate = Decimal(str(contract.get("retention_rate", "0.10")))

        # Parse unit price schedule from contract (if available)
        # Format: {"cost_code": max_price, ...}
        unit_price_schedule = contract.get("unit_price_schedule", {})
        if isinstance(unit_price_schedule, dict):
            unit_price_schedule = {
                k: Decimal(str(v)) for k, v in unit_price_schedule.items()
            }

        # Billing cap
        billing_cap = None
        if contract.get("value"):
            billing_cap = Decimal(str(contract["value"]))

        # Approved cost codes
        approved_cost_codes = contract.get("approved_cost_codes", [])

        return ContractTerm(
            retention_rate=retention_rate,
            unit_price_schedule=unit_price_schedule,
            billing_cap=billing_cap,
            approved_cost_codes=approved_cost_codes,
        )

    def _validate_retention(
        self, invoice: Invoice, contract_terms: ContractTerm
    ) -> List[ComplianceAnomaly]:
        """
        Validate retention calculation.

        Expected retention = invoice.amount × contract.retention_rate
        """
        anomalies = []

        # Calculate expected retention
        expected_retention = invoice.amount * contract_terms.retention_rate

        # Try to find actual retention from invoice
        # This could be in a separate field or in payment terms
        # For now, we'll check if line items include a retention line
        actual_retention = Decimal(0)

        for item in invoice.line_items:
            if "retention" in item.description.lower():
                actual_retention += item.total

        # Allow 1% tolerance for rounding
        tolerance = invoice.amount * Decimal("0.01")

        if abs(expected_retention - actual_retention) > tolerance:
            severity = "high" if abs(expected_retention - actual_retention) > expected_retention * Decimal("0.1") else "medium"

            anomalies.append(
                ComplianceAnomaly(
                    type="retention_violation",
                    severity=severity,
                    message=(
                        f"Retention amount mismatch: expected ${expected_retention:.2f} "
                        f"({contract_terms.retention_rate * 100}% of ${invoice.amount:.2f}), "
                        f"but found ${actual_retention:.2f}"
                    ),
                    contract_id=invoice.contract_id or "UNKNOWN",
                    contract_clause="Retention Rate",
                    expected=float(expected_retention),
                    actual=float(actual_retention),
                    invoice_id=invoice.id,
                )
            )

            logger.warning(
                "Retention violation detected",
                invoice_id=invoice.id,
                expected=expected_retention,
                actual=actual_retention,
            )

        return anomalies

    def _validate_unit_prices(
        self, invoice: Invoice, contract_terms: ContractTerm
    ) -> List[ComplianceAnomaly]:
        """
        Validate line item unit prices against contract schedule.

        Each line item's unit price should not exceed the contract's
        approved unit price for that cost code (within tolerance).
        """
        anomalies = []

        if not contract_terms.unit_price_schedule:
            # No price schedule defined, skip validation
            return anomalies

        for item in invoice.line_items:
            # Check if we have a price schedule for this cost code
            if item.cost_code not in contract_terms.unit_price_schedule:
                # Cost code not in schedule - will be caught by scope validation
                continue

            max_unit_price = contract_terms.unit_price_schedule[item.cost_code]
            tolerance = max_unit_price * contract_terms.price_tolerance_percent

            if item.unit_price > (max_unit_price + tolerance):
                # Price exceeds allowed amount
                overage = item.unit_price - max_unit_price
                overage_percent = (overage / max_unit_price) * 100

                severity = "critical" if overage_percent > 20 else "high" if overage_percent > 10 else "medium"

                anomalies.append(
                    ComplianceAnomaly(
                        type="price_mismatch",
                        severity=severity,
                        message=(
                            f"Unit price for {item.cost_code} exceeds contract schedule: "
                            f"${item.unit_price:.2f} > ${max_unit_price:.2f} "
                            f"({overage_percent:.1f}% over limit)"
                        ),
                        contract_id=invoice.contract_id or "UNKNOWN",
                        contract_clause="Unit Price Schedule",
                        expected=float(max_unit_price),
                        actual=float(item.unit_price),
                        invoice_id=invoice.id,
                        line_item_id=item.id,
                        cost_code=item.cost_code,
                    )
                )

                logger.warning(
                    "Unit price violation",
                    invoice_id=invoice.id,
                    line_item_id=item.id,
                    cost_code=item.cost_code,
                    max_price=max_unit_price,
                    actual_price=item.unit_price,
                )

        return anomalies

    def _validate_billing_cap(
        self, invoice: Invoice, contract: Dict[str, Any], contract_terms: ContractTerm
    ) -> List[ComplianceAnomaly]:
        """
        Validate that total billing doesn't exceed contract cap.

        Sum all invoices for this contract + current invoice should not
        exceed the contract's total value.
        """
        anomalies = []

        if not contract_terms.billing_cap:
            # No billing cap defined
            return anomalies

        # Get sum of all invoices for this contract
        total_billed = self._get_total_billed_for_contract(invoice.contract_id)

        # Add current invoice
        total_with_current = total_billed + invoice.amount

        if total_with_current > contract_terms.billing_cap:
            overage = total_with_current - contract_terms.billing_cap
            overage_percent = (overage / contract_terms.billing_cap) * 100

            severity = "critical" if overage_percent > 10 else "high"

            anomalies.append(
                ComplianceAnomaly(
                    type="billing_cap_exceeded",
                    severity=severity,
                    message=(
                        f"Billing cap exceeded: total billing ${total_with_current:.2f} "
                        f"exceeds contract cap ${contract_terms.billing_cap:.2f} "
                        f"(overage: ${overage:.2f}, {overage_percent:.1f}%)"
                    ),
                    contract_id=invoice.contract_id or "UNKNOWN",
                    contract_clause="Contract Value/Billing Cap",
                    expected=float(contract_terms.billing_cap),
                    actual=float(total_with_current),
                    invoice_id=invoice.id,
                )
            )

            logger.warning(
                "Billing cap exceeded",
                invoice_id=invoice.id,
                contract_id=invoice.contract_id,
                billing_cap=contract_terms.billing_cap,
                total_billed=total_with_current,
            )

        return anomalies

    def _validate_scope(
        self, invoice: Invoice, contract_terms: ContractTerm
    ) -> List[ComplianceAnomaly]:
        """
        Validate that all cost codes are within contract scope.

        Each line item's cost code should be in the contract's
        approved cost codes list.
        """
        anomalies = []

        if not contract_terms.approved_cost_codes:
            # No approved cost codes defined, skip validation
            return anomalies

        for item in invoice.line_items:
            if item.cost_code not in contract_terms.approved_cost_codes:
                anomalies.append(
                    ComplianceAnomaly(
                        type="scope_violation",
                        severity="high",
                        message=(
                            f"Cost code '{item.cost_code}' is not in the approved scope "
                            f"for this contract. Description: {item.description}"
                        ),
                        contract_id=invoice.contract_id or "UNKNOWN",
                        contract_clause="Approved Cost Codes/Scope",
                        expected=contract_terms.approved_cost_codes,
                        actual=item.cost_code,
                        invoice_id=invoice.id,
                        line_item_id=item.id,
                        cost_code=item.cost_code,
                    )
                )

                logger.warning(
                    "Scope violation",
                    invoice_id=invoice.id,
                    line_item_id=item.id,
                    cost_code=item.cost_code,
                    approved_codes=contract_terms.approved_cost_codes,
                )

        return anomalies

    def _get_total_billed_for_contract(self, contract_id: str) -> Decimal:
        """
        Get total amount billed for a contract from all invoices.

        Args:
            contract_id: Contract ID to query

        Returns:
            Total amount billed across all invoices
        """
        query = """
        MATCH (i:Invoice)-[:BELONGS_TO]->(c:Contract {contract_id: $contract_id})
        RETURN sum(i.total_amount) as total_billed
        """

        with self.neo4j.driver.session() as session:
            result = session.run(query, contract_id=contract_id)
            record = result.single()

            if record and record["total_billed"]:
                return Decimal(str(record["total_billed"]))

        return Decimal(0)
