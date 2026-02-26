"""Conversation CRUD endpoints."""

from typing import List

from fastapi import APIRouter, HTTPException

from backend.api.schemas import (
    ConversationResponse,
    ConversationWithMessagesResponse,
    MessageResponse,
    UpdateTitleRequest,
)
from backend.memory.conversation_store import ConversationStore

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation():
    """Create a new empty conversation."""
    store = ConversationStore()
    return store.create_conversation()


@router.get("", response_model=List[ConversationResponse])
async def list_conversations():
    """List all conversations ordered by most recently updated."""
    store = ConversationStore()
    return store.list_conversations()


@router.get("/{conversation_id}", response_model=ConversationWithMessagesResponse)
async def get_conversation(conversation_id: str):
    """Get a conversation with its full message history."""
    store = ConversationStore()
    conv = store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    raw_messages = store.get_all_messages(conversation_id)
    messages = [MessageResponse(**m) for m in raw_messages]
    return ConversationWithMessagesResponse(**conv, messages=messages)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    store = ConversationStore()
    if not store.get_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    store.delete_conversation(conversation_id)


@router.patch("/{conversation_id}/title", response_model=ConversationResponse)
async def update_conversation_title(conversation_id: str, body: UpdateTitleRequest):
    """Update the title of a conversation."""
    store = ConversationStore()
    conv = store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    store.update_title(conversation_id, body.title)
    return store.get_conversation(conversation_id)
