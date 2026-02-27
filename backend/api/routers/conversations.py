"""Conversation CRUD endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import (
    ConversationResponse,
    ConversationWithMessagesResponse,
    MessageResponse,
    UpdateTitleRequest,
)
from backend.auth.dependencies import get_current_user
from backend.memory.conversation_store import ConversationStore

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(current_user: dict = Depends(get_current_user)):
    """Create a new empty conversation."""
    store = ConversationStore()
    return store.create_conversation(user_id=current_user["id"])


@router.get("", response_model=List[ConversationResponse])
async def list_conversations(current_user: dict = Depends(get_current_user)):
    """List all conversations for the authenticated user, most recently updated first."""
    store = ConversationStore()
    return store.list_conversations(user_id=current_user["id"])


@router.get("/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(
    conversation_id: str, current_user: dict = Depends(get_current_user)
):
    """Get a conversation with its full message history."""
    store = ConversationStore()
    conv = store.get_conversation(conversation_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    raw_messages = store.get_all_messages(conversation_id)
    messages = [MessageResponse(**m) for m in raw_messages]
    return ConversationWithMessagesResponse(**conv, messages=messages)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str, current_user: dict = Depends(get_current_user)
):
    """Delete a conversation and all its messages."""
    store = ConversationStore()
    if not store.get_conversation(conversation_id, user_id=current_user["id"]):
        raise HTTPException(status_code=404, detail="Conversation not found")
    store.delete_conversation(conversation_id, user_id=current_user["id"])


@router.patch("/{conversation_id}/title", response_model=ConversationResponse)
async def update_conversation_title(
    conversation_id: str,
    body: UpdateTitleRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update the title of a conversation."""
    store = ConversationStore()
    conv = store.get_conversation(conversation_id, user_id=current_user["id"])
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    store.update_title(conversation_id, body.title, user_id=current_user["id"])
    return store.get_conversation(conversation_id, user_id=current_user["id"])
