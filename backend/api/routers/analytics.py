"""
Analytics endpoints — pre-built dashboards for budget variance,
contractor spend, and invoice aging.
"""

from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from neo4j.time import Date as Neo4jDate

from backend.auth.dependencies import get_current_user
from backend.core.cache import TTLCache
from backend.graph.client import Neo4jClient

logger = structlog.get_logger()

router = APIRouter(prefix="/analytics", tags=["analytics"])

_dashboard_cache = TTLCache(ttl=60)


def _to_float(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _node_get(node, key: str, default=None):
    """Access a property from a Neo4j Node or plain dict."""
    try:
        return node[key]
    except (KeyError, TypeError):
        return default


@router.get("/dashboard")
async def get_analytics_dashboard(
    current_user: dict = Depends(get_current_user),
):
    """
    Return all data needed by the Analytics page in a single request.

    Response shape:
    {
        "summary": {total_invoices, total_invoice_value, contractor_count, budget_count},
        "contractor_spend": [{contractor, invoice_count, total_spend}, ...],
        "invoice_aging": {
            "buckets": {"0-30": N, "31-60": N, "61-90": N, "90+": N},
            "amounts": {"0-30": $, ...}
        },
        "budget_summary": [{
            budget_id, project_id, project_name,
            total_allocated, total_spent, variance_pct, variance_amount,
            lines: [{cost_code, description, allocated, spent, variance_amount, variance_pct}, ...]
        }, ...]
    }
    """
    user_id = current_user["id"]

    cached = _dashboard_cache.get(user_id)
    if cached is not None:
        logger.debug("analytics_dashboard_cache_hit", user_id=user_id)
        return cached

    logger.info("analytics_dashboard_requested", user_id=user_id)

    try:
        neo4j = Neo4jClient()

        # ── Contractor Spend ──────────────────────────────────────────────────
        # WHERE must appear before the first WITH that aggregates.
        contractor_rows = neo4j.run_query(
            """
            MATCH (co:Contractor)-[:ISSUED]->(i:Invoice)
            WHERE i.user_id = $user_id
            WITH co.name AS contractor,
                 COUNT(i)      AS invoice_count,
                 SUM(i.amount) AS total_spend
            RETURN contractor, invoice_count, total_spend
            ORDER BY total_spend DESC
            LIMIT 20
            """,
            parameters={"user_id": user_id},
        )

        # ── Invoice Dates for Aging ───────────────────────────────────────────
        invoice_rows = neo4j.run_query(
            """
            MATCH (i:Invoice)
            WHERE i.user_id = $user_id
            RETURN i.invoice_number AS invoice_number,
                   i.amount         AS amount,
                   i.date           AS invoice_date,
                   i.due_date       AS due_date,
                   i.status         AS status
            """,
            parameters={"user_id": user_id},
        )

        # ── Budget Summary ────────────────────────────────────────────────────
        budget_rows = neo4j.run_query(
            """
            MATCH (b:Budget)
            WHERE b.user_id = $user_id
            OPTIONAL MATCH (b)-[:HAS_LINE]->(bl:BudgetLine)
            RETURN b.budget_id     AS budget_id,
                   b.project_id    AS project_id,
                   b.project_name  AS project_name,
                   b.total_allocated AS total_allocated,
                   b.total_spent   AS total_spent,
                   collect(bl)     AS lines
            ORDER BY b.project_name
            """,
            parameters={"user_id": user_id},
        )

    except Exception as e:
        logger.error("analytics_neo4j_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Analytics query failed: {e}")

    # ── Compute Invoice Aging Buckets ─────────────────────────────────────────
    today = datetime.now(timezone.utc).date()
    aging_buckets = {"0-30": 0, "31-60": 0, "61-90": 0, "90+": 0}
    aging_amounts = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}

    for row in invoice_rows:
        raw_date = row.get("invoice_date")
        amount = _to_float(row.get("amount"))
        if raw_date is None:
            continue
        if isinstance(raw_date, Neo4jDate):
            invoice_date = raw_date.to_native()
        elif isinstance(raw_date, str):
            try:
                invoice_date = datetime.fromisoformat(raw_date).date()
            except ValueError:
                continue
        else:
            continue

        days = (today - invoice_date).days
        bucket = (
            "0-30"
            if days <= 30
            else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
        )
        aging_buckets[bucket] += 1
        aging_amounts[bucket] += amount

    # ── Process Budget Lines ──────────────────────────────────────────────────
    budgets = []
    for row in budget_rows:
        lines = []
        for bl in row.get("lines") or []:
            if bl is None:
                continue
            allocated = _to_float(_node_get(bl, "allocated"))
            spent = _to_float(_node_get(bl, "spent"))
            var_amt = spent - allocated
            var_pct = (var_amt / allocated * 100) if allocated > 0 else 0.0
            lines.append(
                {
                    "cost_code": _node_get(bl, "cost_code", ""),
                    "description": _node_get(bl, "description", ""),
                    "allocated": allocated,
                    "spent": spent,
                    "variance_amount": round(var_amt, 2),
                    "variance_pct": round(var_pct, 2),
                }
            )

        total_allocated = _to_float(row.get("total_allocated"))
        total_spent = _to_float(row.get("total_spent"))
        var_amt = total_spent - total_allocated
        var_pct = (var_amt / total_allocated * 100) if total_allocated > 0 else 0.0

        budgets.append(
            {
                "budget_id": row.get("budget_id", ""),
                "project_id": row.get("project_id", ""),
                "project_name": row.get("project_name", "Unknown"),
                "total_allocated": total_allocated,
                "total_spent": total_spent,
                "variance_pct": round(var_pct, 2),
                "variance_amount": round(var_amt, 2),
                "lines": lines,
            }
        )

    # ── Summary KPIs ──────────────────────────────────────────────────────────
    total_invoice_value = sum(_to_float(r.get("amount")) for r in invoice_rows)

    logger.info(
        "analytics_dashboard_complete",
        invoices=len(invoice_rows),
        contractors=len(contractor_rows),
        budgets=len(budgets),
    )

    result = {
        "summary": {
            "total_invoices": len(invoice_rows),
            "total_invoice_value": total_invoice_value,
            "contractor_count": len(contractor_rows),
            "budget_count": len(budgets),
        },
        "contractor_spend": [
            {
                "contractor": r.get("contractor", "Unknown"),
                "invoice_count": r.get("invoice_count", 0),
                "total_spend": _to_float(r.get("total_spend")),
            }
            for r in contractor_rows
        ],
        "invoice_aging": {
            "buckets": aging_buckets,
            "amounts": aging_amounts,
        },
        "budget_summary": budgets,
    }
    _dashboard_cache.set(user_id, result)
    return result
