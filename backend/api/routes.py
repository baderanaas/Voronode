"""
API router — aggregates all sub-routers.

Import this module's `router` in main.py; the split is transparent to FastAPI.
"""

from fastapi import APIRouter

from backend.api.routers import budgets, chat, conversations, graph, health, workflows

router = APIRouter()

router.include_router(conversations.router)
router.include_router(health.router)
router.include_router(workflows.router)
router.include_router(graph.router)
router.include_router(budgets.router)
router.include_router(chat.router)
