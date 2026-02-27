"""Chat endpoints — unified message + file upload, streaming and non-streaming."""

import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.logging import get_logger
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.agents.orchestrator import create_multi_agent_graph
from backend.api.schemas import ChatResponse, ChatStreamEvent
from backend.auth.dependencies import get_current_user
from backend.core.config import settings
from backend.memory.conversation_store import ConversationStore
from backend.memory.mem0_client import Mem0Client

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)

# ── Non-streaming ──────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(""),
    files: Optional[List[UploadFile]] = File(None),
    conversation_id: str = Form(""),
    session_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Unified conversational AI endpoint — accepts optional file uploads alongside
    an optional text message.

    When files are present the upload graph runs first; if a message is also
    present the chat graph runs afterwards combining both results.
    """
    start_time = time.time()
    original_message = message

    temp_paths: list[str] = []
    uploaded_filenames: list[str] = []
    upload_summary = ""
    prompt_intent = ""
    steps_completed = 0
    upload_display_data = None
    upload_display_format = "text"

    user_id = current_user["id"]

    # ── History + Mem0 context ────────────────────────────────────────────────
    _store = ConversationStore()
    _mem0 = Mem0Client()
    history = (
        _store.get_recent_messages(
            conversation_id, limit=settings.conversation_window_size
        )
        if conversation_id
        else []
    )
    memories_text = await _mem0.search(
        message or "context", limit=settings.memory_search_limit, user_id=user_id
    )

    try:
        if files:
            logger.info("chat_upload_request_received", file_count=len(files))
            file_descriptions = []
            for uploaded_file in files:
                suffix = Path(uploaded_file.filename).suffix or ".tmp"
                content = await uploaded_file.read()
                if len(content) > settings.api_upload_max_size:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File '{uploaded_file.filename}' too large. "
                        f"Maximum size: {settings.api_upload_max_size} bytes",
                    )
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(content)
                    tmp_path = tmp.name
                temp_paths.append(tmp_path)
                uploaded_filenames.append(uploaded_file.filename)
                file_descriptions.append(f"- {uploaded_file.filename} → {tmp_path}")
                logger.info(
                    "chat_upload_temp_saved",
                    filename=uploaded_file.filename,
                    path=tmp_path,
                )

            file_previews = []
            for desc, tmp_path in zip(file_descriptions, temp_paths):
                preview = _extract_file_preview(tmp_path)
                file_previews.append(
                    f"{desc}\n  Content preview: {preview}" if preview else desc
                )

            file_list_str = "\n".join(file_previews)
            count = len(files)
            upload_message = (
                f"User uploaded {count} file(s):\n{file_list_str}\n\n"
                "Please identify and process each document."
            )

            graph = create_multi_agent_graph()
            upload_state = {
                "user_query": upload_message,
                "conversation_history": [],
                "retry_count": 0,
                "current_step": 0,
                "completed_steps": [],
                "react_max_steps": 5,
                "user_id": user_id,
            }
            config = {"configurable": {"thread_id": session_id or "upload_default"}}
            final_upload_state = graph.invoke(upload_state, config)
            upload_summary = final_upload_state.get("final_response", "")
            upload_display_data = final_upload_state.get("display_data")
            upload_display_format = final_upload_state.get("display_format", "text")
            prompt_intent = (
                final_upload_state.get("planner_output", {})
                .get("plan", {})
                .get("intent", "")
                .strip()
            )
            steps_completed = (
                final_upload_state.get("execution_results", {})
                .get("metadata", {})
                .get("steps_completed", 0)
            )

            # Files only — return upload result immediately
            if not original_message.strip():
                # Persist file-only upload as a clean conversation turn
                if conversation_id and uploaded_filenames and upload_summary:
                    synthetic_user = f"[Attached: {', '.join(uploaded_filenames)}]"
                    _store.add_message(conversation_id, "user", synthetic_user)
                    _store.add_message(conversation_id, "assistant", upload_summary)
                    conv = _store.get_conversation(conversation_id, user_id=user_id)
                    if conv and conv["title"] == "New conversation":
                        _store.update_title(conversation_id, uploaded_filenames[0][:60], user_id=user_id)
                    await _mem0.add_turn([
                        {"role": "user", "content": synthetic_user},
                        {"role": "assistant", "content": upload_summary},
                    ], user_id=user_id)
                metadata = {
                    "processing_time_seconds": round(time.time() - start_time, 2),
                    "file_count": count,
                    "retry_count": final_upload_state.get("retry_count", 0),
                }
                logger.info(
                    "chat_upload_complete",
                    processing_time=metadata["processing_time_seconds"],
                )
                return ChatResponse(
                    response=upload_summary,
                    display_format=final_upload_state.get("display_format", "text"),
                    display_data=final_upload_state.get("display_data"),
                    route=final_upload_state.get("route", "unknown"),
                    execution_mode="upload",
                    metadata=metadata,
                    session_id=session_id,
                )

        effective_message = message.strip() or prompt_intent
        full_message = (
            f"{effective_message}\n\n[Context — documents just processed: {upload_summary}]"
            if steps_completed > 0
            else effective_message
        )

        logger.info("chat_request_received", message=full_message[:100])

        graph = create_multi_agent_graph()
        initial_state = {
            "user_query": full_message,
            "conversation_history": history,
            "long_term_memories": memories_text,
            "retry_count": 0,
            "current_step": 0,
            "completed_steps": [],
            "react_max_steps": 5,
            "user_id": user_id,
        }
        config = {"configurable": {"thread_id": session_id or "default"}}
        final_state = graph.invoke(initial_state, config)

        route = final_state.get("route", "unknown")

        if route == "generic_response" and upload_summary:
            planner_text = final_state.get("planner_output", {}).get(
                "response", ""
            ) or final_state.get("final_response", "")
            response_text = planner_text
            display_format = upload_display_format
            display_data = upload_display_data
            logger.info("chat_generic_shortcut", session_id=session_id)
        else:
            response_text = final_state.get("final_response", "")
            display_format = final_state.get("display_format", "text")
            display_data = final_state.get("display_data")

        execution_mode = final_state.get("execution_mode")
        metadata = {
            "processing_time_seconds": round(time.time() - start_time, 2),
            "retry_count": final_state.get("retry_count", 0),
            "react_steps": len(final_state.get("completed_steps", [])),
        }

        logger.info(
            "chat_request_complete",
            route=route,
            execution_mode=execution_mode,
            processing_time=metadata["processing_time_seconds"],
        )

        # ── Persist turn ──────────────────────────────────────────────────────
        if conversation_id:
            if uploaded_filenames and not original_message:
                # File-only upload that triggered second-phase chat via prompt_intent.
                # Save the upload interaction (not the internal chat response).
                synthetic_user = f"[Attached: {', '.join(uploaded_filenames)}]"
                _store.add_message(conversation_id, "user", synthetic_user)
                _store.add_message(conversation_id, "assistant", upload_summary)
                conv = _store.get_conversation(conversation_id, user_id=user_id)
                if conv and conv["title"] == "New conversation":
                    _store.update_title(conversation_id, uploaded_filenames[0][:60], user_id=user_id)
                await _mem0.add_turn([
                    {"role": "user", "content": synthetic_user},
                    {"role": "assistant", "content": upload_summary},
                ], user_id=user_id)
            else:
                # Normal text message (with or without files)
                if original_message:
                    _store.add_message(conversation_id, "user", original_message)
                if response_text:
                    _store.add_message(conversation_id, "assistant", response_text)
                conv = _store.get_conversation(conversation_id, user_id=user_id)
                if conv and conv["title"] == "New conversation" and original_message:
                    _store.update_title(conversation_id, original_message[:60].strip(), user_id=user_id)
                if original_message and response_text:
                    await _mem0.add_turn([
                        {"role": "user", "content": original_message},
                        {"role": "assistant", "content": response_text},
                    ], user_id=user_id)

        return ChatResponse(
            response=response_text,
            display_format=display_format,
            display_data=display_data,
            route=route,
            execution_mode=execution_mode,
            metadata=metadata,
            session_id=session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_request_failed", error=str(e))
        return ChatResponse(
            response=f"I encountered an error while processing your request: {str(e)}",
            display_format="text",
            display_data=None,
            route="generic_response",
            execution_mode=None,
            metadata={
                "error": str(e),
                "processing_time_seconds": round(time.time() - start_time, 2),
            },
            session_id=session_id,
        )
    finally:
        for tmp_path in temp_paths:
            try:
                p = Path(tmp_path)
                if p.exists():
                    p.unlink()
                    logger.debug("chat_temp_cleaned", path=tmp_path)
            except Exception as cleanup_err:
                logger.warning(
                    "chat_cleanup_failed", path=tmp_path, error=str(cleanup_err)
                )


# ── Streaming ──────────────────────────────────────────────────────────────────


@router.post("/chat/stream")
async def chat_stream(
    message: str = Form(""),
    files: Optional[List[UploadFile]] = File(None),
    conversation_id: str = Form(""),
    session_id: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Streaming conversational AI endpoint using Server-Sent Events.

    Events emitted: planner | upload_agent | upload_summary | executor |
                    planner_react | validator | responder | complete | error
    """

    user_id = current_user["id"]

    async def generate_events():
        start_time = time.time()
        temp_paths: list[str] = []
        upload_summary = ""
        upload_display_data = None
        upload_display_format = "text"
        prompt_intent = ""
        steps_completed = 0
        response_text = ""

        # ── History + Mem0 context ────────────────────────────────────────────
        store = ConversationStore()
        mem0 = Mem0Client()
        original_message = message
        uploaded_filenames: list[str] = []

        history = (
            store.get_recent_messages(
                conversation_id, limit=settings.conversation_window_size
            )
            if conversation_id
            else []
        )
        memories_text = await mem0.search(
            message or "context", limit=settings.memory_search_limit, user_id=user_id
        )

        def _emit(node_name: str, state_update: dict) -> str:
            event_data = _create_event_data(node_name, state_update)
            if event_data is None:
                return ""
            event = ChatStreamEvent(
                event=node_name,
                data=event_data,
                timestamp=datetime.now(timezone.utc),
            )
            logger.debug(
                "chat_stream_event_sent", node=node_name, session_id=session_id
            )
            return f"data: {event.model_dump_json()}\n\n"

        try:
            if files:
                logger.info("chat_stream_upload_start", file_count=len(files))
                file_descriptions = []
                for uploaded_file in files:
                    suffix = Path(uploaded_file.filename).suffix or ".tmp"
                    content = await uploaded_file.read()
                    if len(content) > settings.api_upload_max_size:
                        error_event = ChatStreamEvent(
                            event="error",
                            data={
                                "error": f"File '{uploaded_file.filename}' too large.",
                                "message": f"File '{uploaded_file.filename}' exceeds the maximum upload size.",
                            },
                            timestamp=datetime.now(timezone.utc),
                        )
                        yield f"data: {error_event.model_dump_json()}\n\n"
                        return
                    with tempfile.NamedTemporaryFile(
                        delete=False, suffix=suffix
                    ) as tmp:
                        tmp.write(content)
                        tmp_path = tmp.name
                    temp_paths.append(tmp_path)
                    uploaded_filenames.append(uploaded_file.filename)
                    file_descriptions.append(f"- {uploaded_file.filename} → {tmp_path}")
                    logger.info(
                        "chat_stream_temp_saved",
                        filename=uploaded_file.filename,
                        path=tmp_path,
                    )

                file_previews = []
                for desc, tmp_path in zip(file_descriptions, temp_paths):
                    preview = _extract_file_preview(tmp_path)
                    file_previews.append(
                        f"{desc}\n  Content preview: {preview}" if preview else desc
                    )

                file_list_str = "\n".join(file_previews)
                count = len(files)
                upload_message = (
                    f"User uploaded {count} file(s):\n{file_list_str}\n\n"
                    "Please identify and process each document."
                )

                upload_graph = create_multi_agent_graph()
                upload_state = {
                    "user_query": upload_message,
                    "conversation_history": [],
                    "retry_count": 0,
                    "current_step": 0,
                    "completed_steps": [],
                    "react_max_steps": 5,
                    "user_id": user_id,
                }
                upload_config = {
                    "configurable": {"thread_id": f"{session_id or 'stream'}_upload"}
                }

                for chunk in upload_graph.stream(upload_state, upload_config):
                    node_name = list(chunk.keys())[0]
                    state_update = chunk[node_name]

                    if node_name == "planner":
                        prompt_intent = (
                            state_update.get("planner_output", {})
                            .get("plan", {})
                            .get("intent", "")
                            .strip()
                        )
                    elif node_name == "upload_agent":
                        steps_completed = (
                            state_update.get("execution_results", {})
                            .get("metadata", {})
                            .get("steps_completed", 0)
                        )
                    elif node_name == "responder":
                        upload_summary = state_update.get("final_response", "")
                        upload_display_data = state_update.get("display_data")
                        upload_display_format = state_update.get(
                            "display_format", "text"
                        )

                    emit_name = (
                        "upload_summary" if node_name == "responder" else node_name
                    )
                    event_data = _create_event_data(node_name, state_update)
                    if event_data:
                        event = ChatStreamEvent(
                            event=emit_name,
                            data=event_data,
                            timestamp=datetime.now(timezone.utc),
                        )
                        logger.debug(
                            "chat_stream_event_sent",
                            node=emit_name,
                            session_id=session_id,
                        )
                        yield f"data: {event.model_dump_json()}\n\n"

            if not original_message.strip():
                # Persist file-only upload as a clean conversation turn
                if conversation_id and uploaded_filenames and upload_summary:
                    synthetic_user = f"[Attached: {', '.join(uploaded_filenames)}]"
                    store.add_message(conversation_id, "user", synthetic_user)
                    store.add_message(conversation_id, "assistant", upload_summary)
                    conv = store.get_conversation(conversation_id, user_id=user_id)
                    if conv and conv["title"] == "New conversation":
                        store.update_title(conversation_id, uploaded_filenames[0][:60], user_id=user_id)
                    await mem0.add_turn([
                        {"role": "user", "content": synthetic_user},
                        {"role": "assistant", "content": upload_summary},
                    ], user_id=user_id)
                complete_event = ChatStreamEvent(
                    event="complete",
                    data={
                        "message": "Processing complete",
                        "processing_time_seconds": round(time.time() - start_time, 2),
                    },
                    timestamp=datetime.now(timezone.utc),
                )
                yield f"data: {complete_event.model_dump_json()}\n\n"
                return

            effective_message = message.strip() or prompt_intent
            full_message = (
                f"{effective_message}\n\n[Context — documents just processed: {upload_summary}]"
                if steps_completed > 0
                else effective_message
            )

            logger.info("chat_stream_chat_start", message=full_message[:100])

            chat_graph = create_multi_agent_graph()
            initial_state = {
                "user_query": full_message,
                "conversation_history": history,
                "long_term_memories": memories_text,
                "retry_count": 0,
                "current_step": 0,
                "completed_steps": [],
                "react_max_steps": 5,
                "user_id": user_id,
            }
            chat_config = {"configurable": {"thread_id": session_id or "default"}}

            phase_c_route = None
            for chunk in chat_graph.stream(initial_state, chat_config):
                node_name = list(chunk.keys())[0]
                state_update = chunk[node_name]

                if node_name == "planner":
                    phase_c_route = state_update.get("route")
                    if phase_c_route == "generic_response" and upload_summary:
                        planner_text = (
                            state_update.get("planner_output", {}).get("response", "")
                            or upload_summary
                        )
                        response_text = planner_text
                        line = _emit(node_name, state_update)
                        if line:
                            yield line
                        shortcut_event = ChatStreamEvent(
                            event="responder",
                            data={
                                "stage": "formatting",
                                "response": planner_text,
                                "display_format": upload_display_format,
                                "display_data": upload_display_data,
                            },
                            timestamp=datetime.now(timezone.utc),
                        )
                        logger.info(
                            "chat_stream_generic_shortcut", session_id=session_id
                        )
                        yield f"data: {shortcut_event.model_dump_json()}\n\n"
                        break

                if node_name == "responder":
                    response_text = state_update.get("final_response", response_text)

                line = _emit(node_name, state_update)
                if line:
                    yield line

            # ── Persist turn ──────────────────────────────────────────────────
            if conversation_id:
                if uploaded_filenames and not original_message:
                    # File-only upload that triggered second-phase chat via prompt_intent.
                    # Save the upload interaction (not the internal chat response).
                    synthetic_user = f"[Attached: {', '.join(uploaded_filenames)}]"
                    store.add_message(conversation_id, "user", synthetic_user)
                    store.add_message(conversation_id, "assistant", upload_summary)
                    conv = store.get_conversation(conversation_id, user_id=user_id)
                    if conv and conv["title"] == "New conversation":
                        store.update_title(conversation_id, uploaded_filenames[0][:60], user_id=user_id)
                    await mem0.add_turn([
                        {"role": "user", "content": synthetic_user},
                        {"role": "assistant", "content": upload_summary},
                    ], user_id=user_id)
                else:
                    # Normal text message (with or without files)
                    if original_message:
                        store.add_message(conversation_id, "user", original_message)
                    if response_text:
                        store.add_message(conversation_id, "assistant", response_text)
                    conv = store.get_conversation(conversation_id, user_id=user_id)
                    if conv and conv["title"] == "New conversation" and original_message:
                        store.update_title(conversation_id, original_message[:60].strip(), user_id=user_id)
                    if original_message and response_text:
                        await mem0.add_turn([
                            {"role": "user", "content": original_message},
                            {"role": "assistant", "content": response_text},
                        ], user_id=user_id)

            processing_time = time.time() - start_time

            complete_event = ChatStreamEvent(
                event="complete",
                data={
                    "message": "Processing complete",
                    "processing_time_seconds": round(processing_time, 2),
                },
                timestamp=datetime.now(timezone.utc),
            )
            yield f"data: {complete_event.model_dump_json()}\n\n"
            logger.info(
                "chat_stream_complete",
                processing_time=processing_time,
                session_id=session_id,
            )

        except Exception as e:
            logger.error("chat_stream_failed", error=str(e))
            error_event = ChatStreamEvent(
                event="error",
                data={
                    "error": str(e),
                    "message": f"I encountered an error while processing your request: {str(e)}",
                },
                timestamp=datetime.now(timezone.utc),
            )
            yield f"data: {error_event.model_dump_json()}\n\n"

        finally:
            for tmp_path in temp_paths:
                try:
                    p = Path(tmp_path)
                    if p.exists():
                        p.unlink()
                        logger.debug("chat_stream_temp_cleaned", path=tmp_path)
                except Exception as cleanup_err:
                    logger.warning(
                        "chat_stream_cleanup_failed",
                        path=tmp_path,
                        error=str(cleanup_err),
                    )

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Private helpers ────────────────────────────────────────────────────────────


def _create_event_data(
    node_name: str, state_update: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Map a LangGraph node name + state update to an SSE event payload."""
    if node_name == "planner":
        planner_output = state_update.get("planner_output", {})
        return {
            "stage": "planning",
            "route": state_update.get("route"),
            "execution_mode": state_update.get("execution_mode"),
            "plan": planner_output.get("plan", {}),
            "response": planner_output.get("response", ""),
            "retry_count": state_update.get("retry_count", 0),
        }

    if node_name == "executor":
        execution_results = state_update.get("execution_results", {})
        execution_mode = state_update.get("execution_mode", "one_way")
        if execution_mode == "one_way":
            return {
                "stage": "execution",
                "mode": "one_way",
                "status": execution_results.get("status"),
                "results": execution_results.get("results", []),
                "metadata": execution_results.get("metadata", {}),
            }
        completed_steps = state_update.get("completed_steps", [])
        latest_step = completed_steps[-1] if completed_steps else {}
        return {
            "stage": "execution",
            "mode": "react",
            "status": (
                latest_step.get("status", "unknown") if latest_step else "unknown"
            ),
            "current_step": state_update.get("current_step", 0),
            "step_result": latest_step,
            "total_steps": len(completed_steps),
        }

    if node_name == "planner_react":
        completed_steps = state_update.get("completed_steps", [])
        return {
            "stage": "react_planning",
            "continue": state_update.get("react_continue", False),
            "next_step": state_update.get("next_step", {}),
            "current_step": state_update.get("current_step", 0),
            "previous_result": completed_steps[-1] if completed_steps else None,
        }

    if node_name == "validator":
        validation_result = state_update.get("validation_result", {})
        return {
            "stage": "validation",
            "valid": validation_result.get("valid", False),
            "issues": validation_result.get("issues", []),
            "retry_suggestion": validation_result.get("retry_suggestion", ""),
        }

    if node_name == "responder":
        return {
            "stage": "formatting",
            "response": state_update.get("final_response", ""),
            "display_format": state_update.get("display_format", "text"),
            "display_data": state_update.get("display_data"),
        }

    if node_name == "upload_agent":
        execution_results = state_update.get("execution_results", {})
        return {
            "stage": "upload",
            "status": execution_results.get("status"),
            "results": execution_results.get("results", []),
            "metadata": execution_results.get("metadata", {}),
        }

    return None


def _extract_file_preview(file_path: str, max_chars: int = 500) -> str:
    """Extract a short text preview from a file for content-based classification."""
    try:
        path = Path(file_path)
        suffix = path.suffix.lower()

        if suffix == ".pdf":
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                text = ""
                for page in pdf.pages[:2]:
                    text += (page.extract_text() or "") + "\n"
                    if len(text) >= max_chars:
                        break
                return text[:max_chars].strip()

        if suffix == ".csv":
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [line.rstrip() for i, line in enumerate(f) if i < 5]
            return "\n".join(lines)[:max_chars]

        if suffix in (".xlsx", ".xls"):
            import pandas as pd

            df = pd.read_excel(file_path, nrows=5)
            return f"Columns: {', '.join(df.columns)}\n{df.head(3).to_string()}"[
                :max_chars
            ]

    except Exception as e:
        logger.warning("file_preview_extraction_failed", path=file_path, error=str(e))
    return ""
