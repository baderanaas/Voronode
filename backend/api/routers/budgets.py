"""Budget endpoints."""

import structlog
from fastapi import APIRouter, HTTPException

from backend.api.schemas import (
    BudgetDetailResponse,
    BudgetLineResponse,
    BudgetVarianceResponse,
)
from backend.services.graph_builder import GraphBuilder

router = APIRouter(prefix="/budgets", tags=["budgets"])
logger = structlog.get_logger()

_graph_builder = GraphBuilder()


@router.get("/{budget_id}", response_model=BudgetDetailResponse)
async def get_budget(budget_id: str):
    """Get budget details by ID."""
    logger.info("budget_detail_requested", budget_id=budget_id)
    try:
        budget_data = _graph_builder.get_budget_by_id(budget_id)
        if not budget_data:
            raise HTTPException(status_code=404, detail="Budget not found")
        budget_lines = [
            BudgetLineResponse(
                id=line["id"],
                cost_code=line["cost_code"],
                description=line["description"],
                allocated=line["allocated"],
                spent=line["spent"],
                remaining=line["remaining"],
                variance_percent=(
                    ((line["spent"] - line["allocated"]) / line["allocated"] * 100)
                    if line["allocated"] > 0
                    else 0
                ),
            )
            for line in budget_data["budget_lines"]
        ]
        return BudgetDetailResponse(
            id=budget_data["id"],
            project_id=budget_data["project_id"],
            project_name=budget_data["project_name"],
            total_allocated=budget_data["total_allocated"],
            total_spent=budget_data["total_spent"],
            total_remaining=budget_data["total_remaining"],
            line_count=budget_data["line_count"],
            status=budget_data["status"],
            budget_lines=budget_lines,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_detail_failed", budget_id=budget_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve budget: {e}")


@router.get("/project/{project_id}")
async def get_project_budgets(project_id: str):
    """Get all budgets for a project."""
    logger.info("project_budgets_requested", project_id=project_id)
    try:
        budgets = _graph_builder.get_budgets_by_project(project_id)
        return {
            "project_id": project_id,
            "budget_count": len(budgets),
            "budgets": budgets,
        }
    except Exception as e:
        logger.error("project_budgets_failed", project_id=project_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to retrieve budgets: {e}")


@router.get("/{budget_id}/variance", response_model=BudgetVarianceResponse)
async def get_budget_variance(budget_id: str):
    """Calculate budget variance (budget vs actual spend)."""
    logger.info("budget_variance_requested", budget_id=budget_id)
    try:
        budget_data = _graph_builder.get_budget_by_id(budget_id)
        if not budget_data:
            raise HTTPException(status_code=404, detail="Budget not found")

        total_allocated = budget_data["total_allocated"]
        total_spent = budget_data["total_spent"]
        overall_variance = (
            ((total_spent - total_allocated) / total_allocated * 100)
            if total_allocated > 0
            else 0
        )

        line_variances, overrun_lines, underrun_lines, at_risk_lines = [], [], [], []
        for line in budget_data["budget_lines"]:
            allocated, spent = line["allocated"], line["spent"]
            variance_pct = (
                ((spent - allocated) / allocated * 100) if allocated > 0 else 0
            )
            variance_amt = spent - allocated
            utilization_pct = (spent / allocated * 100) if allocated > 0 else 0
            line_variances.append(
                {
                    "cost_code": line["cost_code"],
                    "description": line["description"],
                    "allocated": allocated,
                    "spent": spent,
                    "variance_percent": round(variance_pct, 2),
                    "variance_amount": round(variance_amt, 2),
                    "utilization_percent": round(utilization_pct, 2),
                }
            )
            if variance_amt > 0:
                overrun_lines.append(line["cost_code"])
            elif variance_amt < 0:
                underrun_lines.append(line["cost_code"])
            if utilization_pct > 90:
                at_risk_lines.append(line["cost_code"])

        return BudgetVarianceResponse(
            budget_id=budget_id,
            project_id=budget_data["project_id"],
            project_name=budget_data["project_name"],
            overall_variance=round(overall_variance, 2),
            overall_variance_amount=round(total_spent - total_allocated, 2),
            line_variances=line_variances,
            overrun_lines=overrun_lines,
            underrun_lines=underrun_lines,
            at_risk_lines=at_risk_lines,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("budget_variance_failed", budget_id=budget_id, error=str(e))
        raise HTTPException(
            status_code=500, detail=f"Failed to calculate variance: {e}"
        )
