"""
WebSocket handler — receives PCM audio from ESP32, runs full AI pipeline,
returns JSON display payload + TTS audio filename.
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
    logger.info(f"ESP32 connected: {websocket.client}")

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
                    await websocket.send_text(json.dumps(response))

                elif msg_type == "command":
                    # Direct text command (debug / button shortcut)
                    text = data.get("text", "")
                    if text:
                        response = await _run_pipeline_text(text, db)
                        await websocket.send_text(json.dumps(response))

                elif msg_type == "sync_request":
                    await websocket.send_text(json.dumps({
                        "type": "sync_ack",
                        "message": "Sync triggered"
                    }))
                    # Trigger sheets sync in background
                    from app.services.sheets_service import sheets_service
                    sheets_service.sync_all(db)

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

    # 1. Notify ESP32: thinking
    await ws.send_text(json.dumps({"type": "state", "face": "thinking"}))

    # 2. STT
    transcript = stt_service.transcribe(audio_bytes)
    if not transcript:
        return _error_response("I didn't catch that. Please try again.")

    await ws.send_text(json.dumps({"type": "transcript", "text": transcript}))

    return await _run_pipeline_text(transcript, db, t_start)


async def _run_pipeline_text(transcript: str, db: Session, t_start: float = None) -> dict:
    """Pipeline from text onwards (skips STT)."""
    if t_start is None:
        t_start = time.time()

    # 3. Get sheet names for context
    sheets = db.query(Sheet).all()
    sheet_names = [s.name for s in sheets]

    # 4. Parse intent
    intent_data = await llm_service.parse_intent(transcript, sheet_names)
    intent = intent_data.get("intent", "UNKNOWN")

    # 5. If clarification needed, ask immediately
    clarification = intent_data.get("clarification_needed")
    if clarification and intent_data.get("missing_fields"):
        tts_file = await tts_service.synthesise(clarification)
        return {
            "type": "clarification",
            "transcript": transcript,
            "intent": intent,
            "question": clarification,
            "audio_file": tts_file,
            "display": {"screen": "speaking", "text": clarification},
        }

    # 6. Execute action
    action_summary, follow_up = intent_executor.execute(intent_data, db)

    # 7. Trigger sheets sync for write intents
    _WRITE_INTENTS = {
        "ADD_TASK", "DELETE_TASK", "UPDATE_TASK",
        "SCHEDULE_MEETING", "DELETE_MEETING",
        "NEW_SHEET", "DELETE_SHEET", "SET_REMINDER", "SYNC_NOW",
    }
    if intent in _WRITE_INTENTS:
        from app.services.sheets_service import sheets_service
        sheets_service.sync_all(db)

    # 8. Generate natural response
    response_text = await llm_service.generate_response(action_summary, follow_up)

    # 9. TTS
    tts_file = await tts_service.synthesise(response_text)

    # 10. Log command
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

    return {
        "type": "response",
        "transcript": transcript,
        "intent": intent,
        "response_text": response_text,
        "audio_file": tts_file,
        "follow_up": follow_up,
        "display": {
            "screen": "speaking",
            "face": "speaking",
            "text": response_text,
        },
        "latency_ms": latency_ms,
    }


def _error_response(message: str) -> dict:
    return {
        "type": "error",
        "response_text": message,
        "display": {"screen": "error", "face": "error", "text": message},
    }


async def _send_error(ws: WebSocket, message: str):
    await ws.send_text(json.dumps(_error_response(message)))
