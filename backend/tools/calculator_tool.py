"""
CalculatorTool - Financial calculations and aggregations.

Domain tool for common financial operations on invoices, contracts, and budgets.
"""

import structlog
import statistics
from typing import Dict, Any, Optional, List
from decimal import Decimal

logger = structlog.get_logger()


class CalculatorTool:
    """
    Tool for financial calculations.

    Capabilities:
    - Sum, average, min, max
    - Variance, standard deviation, percentiles
    - Retention calculations
    - Budget variance analysis
    - Custom formulas
    """

    def run(
        self,
        query: str = "",
        action: str = "",
        context: Optional[Dict[str, Any]] = None,
        data: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Perform financial calculations.

        Args:
            query: User's original query
            action: Calculation to perform (e.g., "Calculate total", "Find average")
            context: Previous results with data to calculate on
            data: Direct data to calculate on

        Returns:
            {
                "calculation": "<what was calculated>",
                "result": <numeric result>,
                "details": {...},  # Breakdown of calculation
                "status": "success" | "failed"
            }
        """
        logger.info("calculator_executing", action=action[:100])

        # Extract data from context if not provided directly
        if not data and context and context.get("previous_results"):
            data = self._extract_data_from_context(context["previous_results"])

        if not data:
            return {
                "error": "No data provided for calculation",
                "action": action,
                "status": "failed",
            }

        # Determine calculation type from action
        action_lower = action.lower()

        try:
            if any(keyword in action_lower for keyword in ["sum", "total", "add up"]):
                return self._calculate_sum(data, action)

            elif any(keyword in action_lower for keyword in ["average", "mean", "avg"]):
                return self._calculate_average(data, action)

            elif "variance" in action_lower:
                return self._calculate_variance(data, action)

            elif any(keyword in action_lower for keyword in ["percentile", "quartile"]):
                return self._calculate_percentile(data, action)

            elif any(keyword in action_lower for keyword in ["min", "minimum", "lowest"]):
                return self._calculate_min(data, action)

            elif any(keyword in action_lower for keyword in ["max", "maximum", "highest"]):
                return self._calculate_max(data, action)

            elif "retention" in action_lower:
                return self._calculate_retention(data, action)

            elif "budget" in action_lower and "variance" in action_lower:
                return self._calculate_budget_variance(data, action)

            else:
                # Generic calculation
                return self._calculate_generic(data, action)

        except Exception as e:
            logger.error("calculation_failed", error=str(e), action=action)
            return {
                "error": str(e),
                "action": action,
                "status": "failed",
            }

    def _extract_data_from_context(self, previous_results: List[Dict]) -> List[Dict]:
        """Extract relevant data from previous tool results."""
        data = []

        for result in previous_results:
            if result.get("status") == "success":
                # Check if result contains list of records
                if "results" in result and isinstance(result["results"], list):
                    data.extend(result["results"])
                elif "result" in result and isinstance(result["result"], list):
                    data.extend(result["result"])
                elif isinstance(result.get("result"), dict):
                    data.append(result["result"])

        return data

    def _extract_numeric_values(self, data: List[Dict], field: str = "amount") -> List[float]:
        """Extract numeric values from data for a specific field."""
        values = []

        for record in data:
            # Try common field names
            for key in [field, "amount", "value", "total", "allocated", "spent"]:
                if key in record:
                    try:
                        value = float(record[key])
                        values.append(value)
                        break
                    except (ValueError, TypeError):
                        continue

        return values

    def _calculate_sum(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Calculate sum/total."""
        values = self._extract_numeric_values(data)

        if not values:
            return {"error": "No numeric values found to sum", "status": "failed"}

        total = sum(values)

        logger.info("calculator_sum", total=total, count=len(values))

        return {
            "calculation": "sum",
            "result": total,
            "details": {
                "count": len(values),
                "min": min(values),
                "max": max(values),
            },
            "status": "success",
        }

    def _calculate_average(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Calculate average/mean."""
        values = self._extract_numeric_values(data)

        if not values:
            return {"error": "No numeric values found to average", "status": "failed"}

        avg = statistics.mean(values)

        logger.info("calculator_average", average=avg, count=len(values))

        return {
            "calculation": "average",
            "result": avg,
            "details": {
                "count": len(values),
                "sum": sum(values),
                "min": min(values),
                "max": max(values),
            },
            "status": "success",
        }

    def _calculate_variance(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Calculate variance and standard deviation."""
        values = self._extract_numeric_values(data)

        if len(values) < 2:
            return {"error": "Need at least 2 values for variance", "status": "failed"}

        variance = statistics.variance(values)
        std_dev = statistics.stdev(values)

        logger.info("calculator_variance", variance=variance, std_dev=std_dev)

        return {
            "calculation": "variance",
            "result": variance,
            "details": {
                "variance": variance,
                "standard_deviation": std_dev,
                "mean": statistics.mean(values),
                "count": len(values),
            },
            "status": "success",
        }

    def _calculate_percentile(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Calculate percentile."""
        values = self._extract_numeric_values(data)

        if not values:
            return {"error": "No numeric values found", "status": "failed"}

        # Extract percentile number from action (e.g., "75th percentile")
        import re
        percentile_match = re.search(r'(\d+)(?:th|st|nd|rd)?\s*percentile', action.lower())
        if percentile_match:
            percentile = int(percentile_match.group(1))
        else:
            percentile = 50  # Default to median

        # Calculate percentile
        sorted_values = sorted(values)
        index = (percentile / 100) * (len(sorted_values) - 1)
        lower_index = int(index)
        upper_index = min(lower_index + 1, len(sorted_values) - 1)
        weight = index - lower_index

        result = sorted_values[lower_index] * (1 - weight) + sorted_values[upper_index] * weight

        logger.info("calculator_percentile", percentile=percentile, result=result)

        return {
            "calculation": f"{percentile}th percentile",
            "result": result,
            "details": {
                "percentile": percentile,
                "count": len(values),
                "min": min(values),
                "max": max(values),
            },
            "status": "success",
        }

    def _calculate_min(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Find minimum value."""
        values = self._extract_numeric_values(data)

        if not values:
            return {"error": "No numeric values found", "status": "failed"}

        min_val = min(values)

        return {
            "calculation": "minimum",
            "result": min_val,
            "details": {"count": len(values)},
            "status": "success",
        }

    def _calculate_max(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Find maximum value."""
        values = self._extract_numeric_values(data)

        if not values:
            return {"error": "No numeric values found", "status": "failed"}

        max_val = max(values)

        return {
            "calculation": "maximum",
            "result": max_val,
            "details": {"count": len(values)},
            "status": "success",
        }

    def _calculate_retention(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Calculate total retention amounts."""
        total_retention = 0
        count = 0

        for record in data:
            # Look for contract value and retention rate
            value = record.get("value") or record.get("amount") or record.get("contract_value")
            retention_rate = record.get("retention_rate") or record.get("retention")

            if value and retention_rate:
                retention = float(value) * float(retention_rate)
                total_retention += retention
                count += 1

        if count == 0:
            return {"error": "No retention data found", "status": "failed"}

        return {
            "calculation": "total retention",
            "result": total_retention,
            "details": {
                "contracts_count": count,
            },
            "status": "success",
        }

    def _calculate_budget_variance(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Calculate budget variance (allocated vs spent)."""
        total_allocated = 0
        total_spent = 0
        count = 0

        for record in data:
            allocated = record.get("allocated") or record.get("budget")
            spent = record.get("spent") or record.get("actual")

            if allocated and spent:
                total_allocated += float(allocated)
                total_spent += float(spent)
                count += 1

        if count == 0:
            return {"error": "No budget data found", "status": "failed"}

        variance = total_spent - total_allocated
        variance_percent = (variance / total_allocated * 100) if total_allocated > 0 else 0

        return {
            "calculation": "budget variance",
            "result": variance,
            "details": {
                "allocated": total_allocated,
                "spent": total_spent,
                "variance_amount": variance,
                "variance_percent": variance_percent,
                "items_count": count,
            },
            "status": "success",
        }

    def _calculate_generic(self, data: List[Dict], action: str) -> Dict[str, Any]:
        """Generic calculation handler."""
        values = self._extract_numeric_values(data)

        if not values:
            return {"error": "No numeric values found", "status": "failed"}

        # Return basic statistics
        return {
            "calculation": "statistics",
            "result": {
                "count": len(values),
                "sum": sum(values),
                "average": statistics.mean(values),
                "min": min(values),
                "max": max(values),
            },
            "status": "success",
        }
