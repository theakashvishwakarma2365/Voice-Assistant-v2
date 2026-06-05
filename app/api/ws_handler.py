"""
WebSocket handler — receives PCM audio from ESP32, runs full AI pipeline,
returns JSON display payload + TTS audio filename.

Improvements:
- Real-time status messages (Thinking…, Searching…, Creating…, etc.)
- Confirmation-aware context: injects last assistant action into "yes/no" replies
- Chained intent execution after WEB_SEARCH (create sheet, add tasks)
"""
import json
import time
from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.models import Sheet, CommandLog
from app.services.stt_service import stt_service
from app.services.llm_service import llm_service
from app.services.tts_service import tts_service
from app.services import intent_executor
from app.services.reminder_service import register_connection, unregister_connection
from app.core.logger import logger
from app.services.session_store import session_store, is_affirmative, is_negative
from app.services.mode_service import mode_service


async def _send_status(ws: WebSocket, status: str, detail: str | None = None):
    """Send a real-time status update to the client."""
    payload = {"type": "status", "status": status}
    if detail:
        payload["detail"] = detail
    await ws.send_text(json.dumps(payload))


def _is_affirmative(text: str) -> bool:
    return text.strip().lower() in _AFFIRMATIVE


def _is_negative(text: str) -> bool:
    return text.strip().lower() in _NEGATIVE


async def handle_audio_ws(websocket: WebSocket):
    """
    Main WebSocket endpoint for ESP32 audio streaming.

    Message protocol (ESP32 → server):
      Binary frames  → raw PCM audio (16kHz, 16-bit, mono)
      Text frame     → JSON control message:
                       { "type": "audio_end" }        → process buffered audio
                       { "type": "command", "text": "..." } → text command bypass
                       { "type": "ping" }             → keepalive

    Server → ESP32:
      Text frame     → JSON response payload
    """
    await websocket.accept()
    register_connection(websocket)
    client_host = websocket.client.host if websocket.client else "local"
    client_port = websocket.client.port if websocket.client else "0"
    session_id = websocket.query_params.get("session_id") or f"ws_{client_host}_{client_port}"
    logger.info(f"ESP32 connected: {websocket.client} | session_id: {session_id}")

    audio_buffer = bytearray()
    db: Session = SessionLocal()

    try:
        while True:
            msg = await websocket.receive()

            # ── Binary frame = PCM audio chunk ────────────────────────────────
            if "bytes" in msg and msg["bytes"]:
                audio_buffer.extend(msg["bytes"])

            # ── Text frame = control JSON ─────────────────────────────────────
            elif "text" in msg and msg["text"]:
                data = json.loads(msg["text"])
                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))

                elif msg_type == "audio_end":
                    if not audio_buffer:
                        await _send_error(websocket, "No audio received")
                        continue
                    response = await _run_pipeline(
                        bytes(audio_buffer), db, websocket
                    )
                    audio_buffer.clear()
                    if response is not None:
                        await websocket.send_text(json.dumps(response))

                elif msg_type == "command":
                    # Direct text command (debug / button shortcut)
                    text = data.get("text", "")
                    if text:
                        response = await _run_pipeline_text(text, db, websocket)
                        if response is not None:
                            await websocket.send_text(json.dumps(response))

                elif msg_type == "sync_request":
                    await websocket.send_text(json.dumps({
                        "type": "sync_ack",
                        "message": "Sync triggered"
                    }))
                    # Trigger sheets sync in background
                    from app.services.sheets_service import sheets_service
                    sheets_service.sync_all_background()

    except WebSocketDisconnect:
        logger.info(f"ESP32 disconnected: {websocket.client}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        unregister_connection(websocket)
        db.close()


async def _run_pipeline(audio_bytes: bytes, db: Session, ws: WebSocket) -> dict:
    """Full voice pipeline: PCM → STT → LLM → execute → TTS → response."""
    t_start = time.time()

    await _send_status(ws, "Transcribing…")
    await ws.send_text(json.dumps({"type": "state", "face": "thinking"}))

    # 2. STT
    import asyncio
    transcript = await asyncio.to_thread(stt_service.transcribe, audio_bytes)
    if not transcript:
        return _error_response("I didn't catch that. Please try again.")

    await ws.send_text(json.dumps({"type": "transcript", "text": transcript}))

    client_host = ws.client.host if ws.client else "local"
    client_port = ws.client.port if ws.client else "0"
    session_id = ws.query_params.get("session_id") or f"ws_{client_host}_{client_port}"

    return await _run_pipeline_text(transcript, db, ws, t_start, session_id=session_id)


async def _run_pipeline_text(transcript: str, db: Session, ws: WebSocket, t_start: float = None, session_id: str = None) -> dict:
    """Pipeline from text onwards (skips STT)."""
    if t_start is None:
        t_start = time.time()

    if session_id is None:
        client_host = ws.client.host if ws.client else "local"
        client_port = ws.client.port if ws.client else "0"
        session_id = ws.query_params.get("session_id") or f"ws_{client_host}_{client_port}"

    # ── Confirmation resolution ────────────────────────────────────────────────
    pending = session_store.get_pending(session_id)
    if pending and is_affirmative(transcript):
        return await _handle_confirmation(transcript, db, ws, t_start, accepted=True, session_id=session_id)
    elif pending and is_negative(transcript):
        return await _handle_confirmation(transcript, db, ws, t_start, accepted=False, session_id=session_id)

    # ── 3. Get sheet names for context ────────────────────────────────────────
    await _send_status(ws, "Understanding…")
    sheets = db.query(Sheet).all()
    sheet_names = [s.name for s in sheets]

    # Inject context: if last assistant message was a follow-up question,
    # prefix the transcript with that context so the LLM resolves references
    history = session_store.get_history(session_id)
    augmented_transcript = transcript
    if history:
        last_assistant = next(
            (m["content"] for m in reversed(history) if m["role"] == "assistant"),
            None
        )
        if last_assistant:
            is_short_or_ambiguous = len(transcript.split()) < 4 or any(
                w in transcript.lower().split()
                for w in ["yes", "no", "sure", "them", "those", "that", "it", "ok", "okay", "cancel", "what", "which", "list"]
            )
            if is_short_or_ambiguous:
                augmented_transcript = f"[Previous assistant message: {last_assistant}]\nUser: {transcript}"

    # ── 4. Parse intent ────────────────────────────────────────────────────────
    await _send_status(ws, "Thinking…")
    intent_data = await llm_service.parse_intent(augmented_transcript, sheet_names, history)
    intent = intent_data.get("intent", "UNKNOWN")
    logger.info(f"Intent: {intent} | transcript: '{transcript}'")

    # ── 5. If clarification needed ─────────────────────────────────────────────
    clarification = intent_data.get("clarification_needed")
    if clarification and intent_data.get("missing_fields"):
        session_store.add_message(session_id, "user", transcript)
        session_store.add_message(session_id, "assistant", clarification)
        
        # Send text response immediately
        clarification_payload = {
            "type": "clarification",
            "transcript": transcript,
            "intent": intent,
            "question": clarification,
            "audio_file": None,
            "display": {"screen": "speaking", "text": clarification},
        }
        await ws.send_text(json.dumps(clarification_payload))
        
        # Synthesize audio
        await _send_status(ws, "Generating audio…")
        try:
            tts_file = await tts_service.synthesise(clarification)
            if tts_file:
                await ws.send_text(json.dumps({
                    "type": "audio",
                    "audio_file": tts_file
                }))
        except Exception as e:
            logger.error(f"TTS clarification error: {e}")
        return None

    # ── 5b. Mode gate ─────────────────────────────────────────────────────────
    if not mode_service.is_intent_allowed(session_id, intent):
        blocked_msg = mode_service.get_blocked_message(session_id, intent)
        session_store.add_message(session_id, "user", transcript)
        session_store.add_message(session_id, "assistant", blocked_msg)
        payload = {
            "type": "response", "transcript": transcript, "intent": intent,
            "response_text": blocked_msg, "audio_file": None,
            "display": {"screen": "speaking", "face": "speaking", "text": blocked_msg},
            "latency_ms": int((time.time() - t_start) * 1000),
        }
        await ws.send_text(json.dumps(payload))
        try:
            tts_file = await tts_service.synthesise(blocked_msg)
            if tts_file:
                await ws.send_text(json.dumps({"type": "audio", "audio_file": tts_file}))
        except Exception:
            pass
        return None

    # ── 5c. DND reminder gate ─────────────────────────────────────────────────
    if intent == "reminder" and mode_service.is_dnd(session_id):
        mode_service.queue_dnd_reminder(session_id, transcript)
        dnd_msg = "DND is active. Reminder queued for later."
        session_store.add_message(session_id, "user", transcript)
        session_store.add_message(session_id, "assistant", dnd_msg)
        payload = {
            "type": "response", "transcript": transcript, "intent": intent,
            "response_text": dnd_msg, "audio_file": None,
            "display": {"screen": "speaking", "face": "speaking", "text": dnd_msg},
            "latency_ms": int((time.time() - t_start) * 1000),
        }
        await ws.send_text(json.dumps(payload))
        return None

    # ── 5d. SET_MODE intercept ────────────────────────────────────────────────
    if intent == "SET_MODE":
        mode = (intent_data.get("entities") or {}).get("mode", "chat").lower()
        mode_intro = mode_service.set_mode(session_id, mode)
        dnd_msgs = mode_service.flush_dnd_queue(session_id) if mode != "dnd" else []
        if dnd_msgs:
            mode_intro += f" You had {len(dnd_msgs)} queued reminder(s): " + "; ".join(dnd_msgs)
        session_store.add_message(session_id, "user", transcript)
        session_store.add_message(session_id, "assistant", mode_intro)
        await ws.send_text(json.dumps({
            "type": "response", "transcript": transcript, "intent": intent,
            "response_text": mode_intro, "audio_file": None,
            "mode": mode,
            "display": {"screen": "speaking", "face": "speaking", "text": mode_intro},
            "latency_ms": int((time.time() - t_start) * 1000),
        }))
        try:
            tts_file = await tts_service.synthesise(mode_intro)
            if tts_file:
                await ws.send_text(json.dumps({"type": "audio", "audio_file": tts_file}))
        except Exception:
            pass
        return None

    # ── 6. Status message per intent ──────────────────────────────────────────
    _INTENT_STATUS = {
        "ADD_TASK": "Adding task…",
        "DELETE_TASK": "Deleting task…",
        "UPDATE_TASK": "Updating task…",
        "QUERY_TASKS": "Looking up tasks…",
        "SCHEDULE_MEETING": "Scheduling meeting…",
        "DELETE_MEETING": "Removing meeting…",
        "UPDATE_MEETING": "Updating meeting…",
        "QUERY_MEETINGS": "Looking up meetings…",
        "NEW_SHEET": "Creating sheet…",
        "DELETE_SHEET": "Deleting sheet…",
        "SWITCH_SHEET": "Switching sheet…",
        "LIST_SHEETS": "Listing sheets…",
        "SET_REMINDER": "Setting reminder…",
        "DELETE_REMINDER": "Removing reminder…",
        "UPDATE_REMINDER": "Updating reminder…",
        "POMODORO_START": "Starting timer…",
        "POMODORO_STOP": "Stopping timer…",
        "POMODORO_PAUSE": "Pausing timer…",
        "POMODORO_RESUME": "Resuming timer…",
        "NOTE_CREATE": "Writing note…",
        "NOTE_READ": "Reading notes…",
        "NOTE_UPDATE": "Updating note…",
        "NOTE_DELETE": "Deleting note…",
        "QUERY_NOTES": "Searching notes…",
        "MORNING_BRIEFING": "Preparing briefing…",
        "SYNC_NOW": "Syncing to Google Sheets…",
        "WEB_SEARCH": "Searching the web…",
        "CHAT": "Thinking…",
        "UNKNOWN": "Thinking…",
    }
    await _send_status(ws, _INTENT_STATUS.get(intent, "Processing…"), detail=intent)

    # ── 7a. WEB_SEARCH: execute inline, stream raw results immediately ─────────
    raw_search_results: list[dict] = []
    if intent == "WEB_SEARCH":
        entities = intent_data.get("entities") or {}
        search_query = entities.get("remarks") or entities.get("title") or transcript

        from app.services.search_service import search_service
        try:
            raw_search_results = await search_service.search(search_query, max_results=5)
        except Exception as e:
            logger.error(f"Search error: {e}")
            raw_search_results = []

        # Stream search results immediately to the client for display
        await ws.send_text(json.dumps({
            "type": "search_results",
            "query": search_query,
            "results": raw_search_results,
            "count": len(raw_search_results),
        }))

        if not raw_search_results:
            action_summary = f"I searched the web for '{search_query}' but couldn't find any relevant results."
            follow_up = None
            debug_steps = None
        else:
            lines = [f"Web search results for '{search_query}':"]
            for idx, r in enumerate(raw_search_results, 1):
                lines.append(f"[{idx}] {r['title']}\n{r['body']}")
            action_summary = "\n\n".join(lines)
            follow_up = (intent_data.get("suggested_followups") or [None])[0]
            debug_steps = None

            # Research mode: auto-save results as a note
            if mode_service.should_save_search_as_note(session_id):
                from app.models.models import Note
                note_content = "\n\n".join(
                    f"**{r['title']}**\n{r['body']}\nSource: {r.get('href','')}"
                    for r in raw_search_results
                )
                note = Note(title=f"Research: {search_query[:80]}", content=note_content)
                db.add(note)
                db.commit()
                debug_steps = [f"Research mode: saved search results as note '{note.title}'"]

        followups = intent_data.get("suggested_followups", [])
        if followups:
            session_store.set_pending(session_id, {
                "follow_up": followups[0],
                "search_summary": action_summary,
                "search_query": search_query,
                "suggested_followups": followups,
            })

    # ── 7b. All other intents: execute normally ────────────────────────────────
    else:
        action_summary, follow_up, debug_steps = await intent_executor.execute(intent_data, db, transcript)
        followups = intent_data.get("suggested_followups", [])

    # ── 8. Handle no-action (CHAT / UNKNOWN fallback) ─────────────────────────
    if action_summary is None:
        await _send_status(ws, "Responding…")
        pending = session_store.get_pending(session_id)
        context = pending.get("search_summary") if pending else None
        response_text = await llm_service.generate_chat_response(transcript, history, context=context)
        action_summary = response_text
    elif intent == "WEB_SEARCH":
        await _send_status(ws, "Responding…")
        response_text = await llm_service.generate_response(action_summary, follow_up)
    else:
        # Productivity actions: use the human-friendly executor summary directly!
        response_text = action_summary
        if follow_up:
            response_text += f" {follow_up}"

    session_store.add_message(session_id, "user", transcript)
    session_store.add_message(session_id, "assistant", response_text)

    # ── 10. Trigger sheets sync for write intents ──────────────────────────────
    _WRITE_INTENTS = {
        "ADD_TASK", "DELETE_TASK", "UPDATE_TASK",
        "SCHEDULE_MEETING", "DELETE_MEETING",
        "NEW_SHEET", "DELETE_SHEET", "SET_REMINDER", "SYNC_NOW",
    }
    if intent in _WRITE_INTENTS:
        await _send_status(ws, "Syncing to Sheets…")
        from app.services.sheets_service import sheets_service
        sheets_service.sync_all_background()

    # ── 11. TTS ────────────────────────────────────────────────────────────────
    # ── 12. Log command ────────────────────────────────────────────────────────
    latency_ms = int((time.time() - t_start) * 1000)
    db.add(CommandLog(
        transcript=transcript,
        intent=intent,
        entities_json=str(intent_data.get("entities", {})),
        success=True,
        response_text=response_text,
        latency_ms=latency_ms,
    ))
    db.commit()

    logger.info(f"Pipeline done in {latency_ms}ms | intent={intent}")

    payload = {
        "type": "response",
        "transcript": transcript,
        "intent": intent,
        "response_text": response_text,
        "audio_file": None,
        "follow_up": follow_up,
        "mode": mode_service.get_mode(session_id),
        "display": {
            "screen": "speaking",
            "face": "speaking",
            "text": response_text,
        },
        "latency_ms": latency_ms,
    }
    if raw_search_results:
        payload["search_results"] = raw_search_results
    if debug_steps:
        payload["debug_steps"] = debug_steps
    if followups:
        payload["suggested_followups"] = followups

    # Send response text immediately
    await ws.send_text(json.dumps(payload))

    # ── 11. TTS ────────────────────────────────────────────────────────────────
    await _send_status(ws, "Generating audio…")
    try:
        tts_file = await tts_service.synthesise(response_text)
        if tts_file:
            await ws.send_text(json.dumps({
                "type": "audio",
                "audio_file": tts_file
            }))
    except Exception as e:
        logger.error(f"TTS error: {e}")

    return None


async def _handle_confirmation(
    transcript: str, db: Session, ws: WebSocket,
    t_start: float, accepted: bool, session_id: str
) -> dict:
    """
    Handle 'yes'/'no' after a follow-up suggestion.
    If accepted, chains into the most relevant action based on search context.
    """
    pending = session_store.get_pending(session_id)
    follow_up_text = pending.get("follow_up", "")

    if not accepted:
        session_store.pop_pending(session_id)
        response_text = "Alright, no problem! What else can I help you with?"
        
        # Send text response immediately
        payload = {
            "type": "response",
            "transcript": transcript,
            "intent": "CHAT",
            "response_text": response_text,
            "audio_file": None,
            "display": {"screen": "speaking", "face": "speaking", "text": response_text},
            "latency_ms": int((time.time() - t_start) * 1000),
        }
        await ws.send_text(json.dumps(payload))
        
        # Synthesize audio
        await _send_status(ws, "Generating audio…")
        try:
            tts_file = await tts_service.synthesise(response_text)
            if tts_file:
                await ws.send_text(json.dumps({
                    "type": "audio",
                    "audio_file": tts_file
                }))
        except Exception as e:
            logger.error(f"TTS negative confirmation error: {e}")

        session_store.add_message(session_id, "user", transcript)
        session_store.add_message(session_id, "assistant", response_text)
        return None

    # Accepted! Determine what was being confirmed from the follow-up text
    await _send_status(ws, "Processing confirmation…", detail=follow_up_text)

    sheets = db.query(Sheet).all()
    sheet_names = [s.name for s in sheets]
    history = session_store.get_history(session_id)

    # Build a chained instruction: "yes, go ahead and [follow_up]"
    search_summary = pending.get("search_summary", "")
    search_query = pending.get("search_query", "")
    chained_prompt = (
        f"The user confirmed: '{follow_up_text}'. "
        f"Context from previous search results: {search_summary[:500]}. "
        f"Original search query was: '{search_query}'. "
        f"Execute the appropriate action now."
    )

    await _send_status(ws, "Thinking…")
    chained_intent = await llm_service.parse_intent(chained_prompt, sheet_names, history)
    chained_intent_name = chained_intent.get("intent", "UNKNOWN")

    await _send_status(ws, _INTENT_STATUS_MAP.get(chained_intent_name, "Processing…"), detail=chained_intent_name)

    session_store.pop_pending(session_id)
    action_summary, new_follow_up, debug_steps = await intent_executor.execute(
        chained_intent, db, chained_prompt
    )

    # If chained intent also failed to resolve, fall back to chat
    if action_summary is None:
        response_text = await llm_service.generate_chat_response(
            f"User confirmed: {follow_up_text}", history
        )
    else:
        response_text = await llm_service.generate_response(action_summary, new_follow_up)

    session_store.add_message(session_id, "user", transcript)
    session_store.add_message(session_id, "assistant", response_text)

    _WRITE_INTENTS = {
        "ADD_TASK", "DELETE_TASK", "UPDATE_TASK",
        "SCHEDULE_MEETING", "DELETE_MEETING",
        "NEW_SHEET", "DELETE_SHEET", "SET_REMINDER", "SYNC_NOW",
    }
    if chained_intent_name in _WRITE_INTENTS:
        await _send_status(ws, "Syncing to Sheets…")
        from app.services.sheets_service import sheets_service
        sheets_service.sync_all_background()

    latency_ms = int((time.time() - t_start) * 1000)
    db.add(CommandLog(
        transcript=transcript,
        intent=f"CONFIRM→{chained_intent_name}",
        entities_json=str(chained_intent.get("entities", {})),
        success=True,
        response_text=response_text,
        latency_ms=latency_ms,
    ))
    db.commit()

    payload = {
        "type": "response",
        "transcript": transcript,
        "intent": chained_intent_name,
        "response_text": response_text,
        "audio_file": None,
        "follow_up": new_follow_up,
        "display": {"screen": "speaking", "face": "speaking", "text": response_text},
        "latency_ms": latency_ms,
        **({"debug_steps": debug_steps} if debug_steps else {}),
    }
    await ws.send_text(json.dumps(payload))

    await _send_status(ws, "Generating audio…")
    try:
        tts_file = await tts_service.synthesise(response_text)
        if tts_file:
            await ws.send_text(json.dumps({
                "type": "audio",
                "audio_file": tts_file
            }))
    except Exception as e:
        logger.error(f"TTS positive confirmation error: {e}")

    return None


# Status label map used by _handle_confirmation
_INTENT_STATUS_MAP = {
    "ADD_TASK": "Adding task…", "DELETE_TASK": "Deleting task…",
    "UPDATE_TASK": "Updating task…", "QUERY_TASKS": "Looking up tasks…",
    "SCHEDULE_MEETING": "Scheduling meeting…", "DELETE_MEETING": "Removing meeting…",
    "UPDATE_MEETING": "Updating meeting…", "QUERY_MEETINGS": "Looking up meetings…",
    "NEW_SHEET": "Creating sheet…", "DELETE_SHEET": "Deleting sheet…",
    "SWITCH_SHEET": "Switching sheet…", "LIST_SHEETS": "Listing sheets…",
    "SET_REMINDER": "Setting reminder…", "DELETE_REMINDER": "Removing reminder…",
    "UPDATE_REMINDER": "Updating reminder…",
    "POMODORO_START": "Starting timer…", "POMODORO_STOP": "Stopping timer…",
    "POMODORO_PAUSE": "Pausing timer…", "POMODORO_RESUME": "Resuming timer…",
    "NOTE_CREATE": "Writing note…", "NOTE_READ": "Reading notes…",
    "NOTE_UPDATE": "Updating note…", "NOTE_DELETE": "Deleting note…",
    "QUERY_NOTES": "Searching notes…",
    "MORNING_BRIEFING": "Preparing briefing…", "SYNC_NOW": "Syncing to Google Sheets…",
    "WEB_SEARCH": "Searching the web…", "SET_MODE": "Setting mode…",
    "CHAT": "Responding…", "UNKNOWN": "Processing…",
}


def _error_response(message: str) -> dict:
    return {
        "type": "error",
        "response_text": message,
        "display": {"screen": "error", "face": "error", "text": message},
    }


async def _send_error(ws: WebSocket, message: str):
    await ws.send_text(json.dumps(_error_response(message)))
