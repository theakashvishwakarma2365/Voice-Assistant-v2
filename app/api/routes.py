"""
REST API routes — tasks, meetings, sheets, reminders, pomodoro, status, offline batch.
"""
import time
import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.models import Sheet, Task, Meeting, Reminder, PomodoroSession, Note
from app.models.schemas import (
    SheetCreate, SheetOut,
    TaskCreate, TaskUpdate, TaskOut,
    MeetingCreate, MeetingUpdate, MeetingOut,
    ReminderCreate, ReminderUpdate, ReminderOut,
    NoteCreate, NoteUpdate, NoteOut,
    PomodoroStart, PomodoroOut,
    ModeSet, ModeOut,
    OfflineBatch, ServerStatus,
)
from app.services.sheets_service import sheets_service
from app.services.stt_service import stt_service
from app.services.llm_service import llm_service
from app.services.tts_service import tts_service
from app.services import intent_executor
from app.models.database import get_db
from sqlalchemy.orm import Session
import os, json
from app.core.config import settings
from app.core.logger import logger
from app.services.session_store import session_store, is_affirmative, is_negative, resolve_confirmation_action
from app.services.mode_service import mode_service

router = APIRouter()
_start_time = time.time()


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/status", response_model=ServerStatus)
async def get_status(db: Session = Depends(get_db)):
    pending_reminders = db.query(Reminder).filter(Reminder.delivered == False).count()
    cache_dir = Path(settings.audio_cache_dir)
    cache_mb = sum(f.stat().st_size for f in cache_dir.glob("*.wav")) / (1024 * 1024) if cache_dir.exists() else 0.0
    return ServerStatus(
        status="ok",
        uptime_seconds=round(time.time() - _start_time, 1),
        whisper_loaded=stt_service.is_loaded,
        ollama_reachable=await llm_service.is_reachable(),
        sheets_connected=sheets_service.is_connected,
        db_ok=True,
        pending_reminders=pending_reminders,
        audio_cache_mb=round(cache_mb, 2),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LLM / Chat helpers (for UI testing)
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/parse_intent")
async def parse_intent_endpoint(body: dict):
    """Parse a free-text transcript via the LLM service.

    Body JSON: { "transcript": "...", "available_sheets": ["Work"], "history": [{"role":"user","content":"..."}]} }
    """
    transcript = body.get("transcript", "")
    available_sheets = body.get("available_sheets", []) or []
    history = body.get("history")
    result = await llm_service.parse_intent(transcript, available_sheets, history)
    return result


@router.post("/generate_response")
async def generate_response_endpoint(body: dict):
    """Generate a short spoken-style response for an action summary.

    Body JSON: { "action_summary": "...", "follow_up": "..." }
    """
    action_summary = body.get("action_summary", "")
    follow_up = body.get("follow_up")
    text = await llm_service.generate_response(action_summary, follow_up)
    return {"response": text}


@router.post("/chat")
async def chat_endpoint(body: dict, db: Session = Depends(get_db)):
    """Unified chat API: parse intent, optionally execute, generate response, and log.

    Body JSON: { "transcript": str, "available_sheets": [...], "execute": bool, "session_id": str }
    """
    transcript = body.get("transcript", "")
    available_sheets = body.get("available_sheets", []) or []
    execute_flag = bool(body.get("execute", False))
    session_id = body.get("session_id", "default")
    history = body.get("history")

    # Initialize session history from body if it is currently empty
    if history and not session_store.get_history(session_id):
        session_store.set_history(session_id, history)

    session_history = session_store.get_history(session_id)

    action_summary = None
    follow_up = None
    debug_steps = None
    raw_search_results: list[dict] = []
    intent = "UNKNOWN"
    assist = ""
    parsed = {}

    # Check for pending confirmations first
    pending = session_store.get_pending(session_id)
    resolved_confirmation = False

    if pending and execute_flag:
        if is_affirmative(transcript):
            res = await resolve_confirmation_action(session_id, transcript, db, accepted=True)
            intent = res.get("intent", "UNKNOWN")
            action_summary = res.get("action_summary")
            assist = res.get("response_text", "")
            follow_up = res.get("follow_up")
            debug_steps = res.get("debug_steps")
            sheets_sync = res.get("sheets_sync", False)
            if sheets_sync:
                from app.services.sheets_service import sheets_service
                sheets_service.sync_all_background()
            resolved_confirmation = True
            parsed = {"intent": intent, "entities": res.get("entities", {}), "suggested_followups": [follow_up] if follow_up else []}
        elif is_negative(transcript):
            res = await resolve_confirmation_action(session_id, transcript, db, accepted=False)
            intent = res.get("intent", "UNKNOWN")
            action_summary = res.get("action_summary")
            assist = res.get("response_text", "")
            follow_up = res.get("follow_up")
            debug_steps = res.get("debug_steps")
            resolved_confirmation = True
            parsed = {"intent": intent, "entities": {}, "suggested_followups": []}

    if not resolved_confirmation:
        parsed = await llm_service.parse_intent(transcript, available_sheets, session_history)
        intent = parsed.get("intent", "UNKNOWN")

        if execute_flag:
            if parsed.get("missing_fields"):
                assist = parsed.get("clarification_needed") or "I need more information before I can do that."
                session_store.add_message(session_id, "user", transcript)
                session_store.add_message(session_id, "assistant", assist)
            else:
                try:
                    # Intercept WEB_SEARCH: run search inline and return raw results
                    if intent == "WEB_SEARCH":
                        from app.services.search_service import search_service
                        entities = parsed.get("entities") or {}
                        search_query = entities.get("remarks") or entities.get("title") or transcript
                        raw_search_results = await search_service.search(search_query, max_results=5)
                        if raw_search_results:
                            lines = [f"Web search results for '{search_query}':"]
                            for idx, r in enumerate(raw_search_results, 1):
                                lines.append(f"[{idx}] {r['title']}\n{r['body']}")
                            action_summary = "\n\n".join(lines)
                        else:
                            action_summary = f"I searched the web for '{search_query}' but couldn't find any relevant results."
                        
                        followups = parsed.get("suggested_followups", [])
                        follow_up = followups[0] if followups else None
                        assist = await llm_service.generate_response(action_summary, follow_up)
                    else:
                        action_summary, follow_up, debug_steps = await intent_executor.execute(parsed, db, transcript)
                        if action_summary is None:
                            pending = session_store.get_pending(session_id)
                            context = pending.get("search_summary") if pending else None
                            assist = await llm_service.generate_chat_response(transcript, session_history, context=context)
                            action_summary = assist
                        elif intent == "WEB_SEARCH":
                            assist = await llm_service.generate_response(action_summary, follow_up)
                        else:
                            assist = action_summary
                            if follow_up:
                                assist += f" {follow_up}"

                    session_store.add_message(session_id, "user", transcript)
                    session_store.add_message(session_id, "assistant", assist)

                    # Store pending confirmation if suggested follow-ups exist
                    followups = parsed.get("suggested_followups", [])
                    if followups:
                        entities = parsed.get("entities") or {}
                        search_query = entities.get("remarks") or entities.get("title") or transcript
                        session_store.set_pending(session_id, {
                            "follow_up": followups[0],
                            "search_summary": action_summary,
                            "search_query": search_query,
                            "suggested_followups": followups,
                        })
                except Exception as e:
                    assist = f"Execution error: {e}"
        else:
            assist = await llm_service.generate_response(transcript, None)
            session_store.add_message(session_id, "user", transcript)
            session_store.add_message(session_id, "assistant", assist)

    # Sync Sheets if write intent (excluding confirmation which is already handled above)
    if not resolved_confirmation and execute_flag:
        _WRITE_INTENTS = {
            "ADD_TASK", "DELETE_TASK", "UPDATE_TASK",
            "SCHEDULE_MEETING", "DELETE_MEETING",
            "NEW_SHEET", "DELETE_SHEET", "SET_REMINDER", "SYNC_NOW",
        }
        if intent in _WRITE_INTENTS:
            from app.services.sheets_service import sheets_service
            sheets_service.sync_all_background()

    # Generate TTS audio
    tts_file = None
    try:
        tts_file = await tts_service.synthesise(assist)
    except Exception as e:
        logger.error(f"TTS error in chat endpoint: {e}")

    # Persist chat log
    try:
        os.makedirs('logs', exist_ok=True)
        entry = {
            'ts': __import__('datetime').datetime.utcnow().isoformat(),
            'transcript': transcript,
            'parsed': parsed,
            'executed': execute_flag,
            'action_summary': action_summary,
            'assistant': assist,
            'session_id': session_id,
        }
        with open('logs/chat.log', 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass

    result = {
        "parsed": parsed,
        "action_summary": action_summary,
        "assistant": assist,
        "audio_file": tts_file,
        "debug_steps": debug_steps if execute_flag else None,
        "session_history": session_store.get_history(session_id)
    }
    if raw_search_results:
        result["search_results"] = raw_search_results
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO FILES (served to ESP32 for TTS playback)
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/audio/{filename}")
async def get_audio(filename: str):
    path = Path(settings.audio_cache_dir) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(str(path), media_type="audio/wav")


# ═══════════════════════════════════════════════════════════════════════════════
# SHEETS
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/sheets", response_model=List[SheetOut])
def list_sheets(db: Session = Depends(get_db)):
    return db.query(Sheet).all()


@router.post("/sheets", response_model=SheetOut)
def create_sheet(body: SheetCreate, db: Session = Depends(get_db)):
    if db.query(Sheet).filter(Sheet.name == body.name).first():
        raise HTTPException(status_code=400, detail="Sheet already exists")
    sheet = Sheet(
        name=body.name,
        tab_name=body.name,
        color_tag=body.color_tag,
        custom_columns=body.custom_columns,
    )
    db.add(sheet)
    db.commit()
    db.refresh(sheet)
    sheets_service.ensure_tab_with_headers(sheet)
    return sheet


@router.delete("/sheets/{sheet_id}")
def delete_sheet(sheet_id: int, db: Session = Depends(get_db)):
    sheet = db.query(Sheet).filter(Sheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Sheet not found")
    db.delete(sheet)
    db.commit()
    return {"message": f"Sheet '{sheet.name}' deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# TASKS
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/tasks", response_model=List[TaskOut])
def list_tasks(
    sheet_id: Optional[int] = Query(None),
    status: Optional[str]   = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Task)
    if sheet_id:
        q = q.filter(Task.sheet_id == sheet_id)
    if status:
        q = q.filter(Task.status == status)
    return q.order_by(Task.due_date.asc().nullslast()).all()


@router.post("/tasks", response_model=TaskOut)
def create_task(body: TaskCreate, db: Session = Depends(get_db)):
    task = Task(**body.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(task, field, value)
    task.synced = False
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Task deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# MEETINGS
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/meetings", response_model=List[MeetingOut])
def list_meetings(
    sheet_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Meeting)
    if sheet_id:
        q = q.filter(Meeting.sheet_id == sheet_id)
    return q.order_by(Meeting.meeting_date.asc().nullslast()).all()


@router.post("/meetings", response_model=MeetingOut)
def create_meeting(body: MeetingCreate, db: Session = Depends(get_db)):
    meeting = Meeting(**body.model_dump())
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


@router.patch("/meetings/{meeting_id}", response_model=MeetingOut)
def update_meeting(meeting_id: int, body: MeetingUpdate, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(meeting, field, value)
    meeting.synced = False
    db.commit()
    db.refresh(meeting)
    return meeting


@router.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    db.delete(meeting)
    db.commit()
    return {"message": "Meeting deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# REMINDERS
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/reminders", response_model=List[ReminderOut])
def list_reminders(db: Session = Depends(get_db)):
    return db.query(Reminder).filter(Reminder.delivered == False).all()


@router.post("/reminders", response_model=ReminderOut)
def create_reminder(body: ReminderCreate, db: Session = Depends(get_db)):
    reminder = Reminder(**body.model_dump())
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
def update_reminder(reminder_id: int, body: ReminderUpdate, db: Session = Depends(get_db)):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(reminder, field, value)
    db.commit()
    db.refresh(reminder)
    return reminder


@router.delete("/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, db: Session = Depends(get_db)):
    reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    db.delete(reminder)
    db.commit()
    return {"message": "Reminder deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# NOTES
# ═══════════════════════════════════════════════════════════════════════════════
import json as _json

@router.get("/notes", response_model=List[NoteOut])
def list_notes(q: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(Note)
    if q:
        query = query.filter(Note.title.ilike(f"%{q}%") | Note.content.ilike(f"%{q}%"))
    notes = query.order_by(Note.created_at.desc()).all()
    result = []
    for n in notes:
        tags = None
        if n.tags:
            try:
                tags = _json.loads(n.tags)
            except Exception:
                tags = [n.tags]
        result.append(NoteOut(
            id=n.id, title=n.title, content=n.content,
            tags=tags, created_at=n.created_at, updated_at=n.updated_at,
        ))
    return result


@router.post("/notes", response_model=NoteOut)
def create_note(body: NoteCreate, db: Session = Depends(get_db)):
    note = Note(
        title=body.title,
        content=body.content,
        tags=_json.dumps(body.tags) if body.tags else None,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    tags = _json.loads(note.tags) if note.tags else None
    return NoteOut(id=note.id, title=note.title, content=note.content,
                   tags=tags, created_at=note.created_at, updated_at=note.updated_at)


@router.get("/notes/{note_id}", response_model=NoteOut)
def get_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    tags = _json.loads(note.tags) if note.tags else None
    return NoteOut(id=note.id, title=note.title, content=note.content,
                   tags=tags, created_at=note.created_at, updated_at=note.updated_at)


@router.patch("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, body: NoteUpdate, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    if body.title is not None:
        note.title = body.title
    if body.content is not None:
        note.content = body.content
    if body.tags is not None:
        note.tags = _json.dumps(body.tags)
    db.commit()
    db.refresh(note)
    tags = _json.loads(note.tags) if note.tags else None
    return NoteOut(id=note.id, title=note.title, content=note.content,
                   tags=tags, created_at=note.created_at, updated_at=note.updated_at)


@router.delete("/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    db.delete(note)
    db.commit()
    return {"message": "Note deleted"}


# ═══════════════════════════════════════════════════════════════════════════════
# OFFLINE BATCH SYNC (from ESP32 SD card queue)
# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/offline_batch")
async def offline_batch(body: OfflineBatch, db: Session = Depends(get_db)):
    """
    Receives queued items from ESP32 SD card when connectivity is restored.
    Processes each item as if it came from a live voice command.
    """
    processed = 0
    errors = 0
    for item in body.items:
        try:
            data = item.data
            if item.type == "task":
                sheet = db.query(Sheet).filter(Sheet.name == data.get("sheet", "Inbox")).first()
                task = Task(
                    sheet_id=sheet.id if sheet else 1,
                    title=data.get("title", "Offline task"),
                    status=data.get("status", "pending"),
                    due_date=datetime.fromisoformat(data["due_date"]) if data.get("due_date") else None,
                    priority=data.get("priority", "normal"),
                    remarks=data.get("remarks"),
                )
                db.add(task)
            elif item.type == "meeting":
                sheet = db.query(Sheet).filter(Sheet.name == data.get("sheet", "Inbox")).first()
                meeting = Meeting(
                    sheet_id=sheet.id if sheet else 1,
                    title=data.get("title", "Offline meeting"),
                    meeting_date=datetime.fromisoformat(data["meeting_date"]) if data.get("meeting_date") else None,
                    participants=data.get("participants"),
                    remarks=data.get("remarks"),
                )
                db.add(meeting)
            processed += 1
        except Exception as e:
            logger.error(f"Offline batch item error: {e}")
            errors += 1

    db.commit()
    sheets_service.sync_all_background()
    logger.info(f"Offline batch: {processed} processed, {errors} errors")
    return {"processed": processed, "errors": errors}


# ═══════════════════════════════════════════════════════════════════════════════
# SYNC
# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/sync")
def force_sync(db: Session = Depends(get_db)):
    sheets_service.sync_all_background()
    return {"message": "Sync triggered", "timestamp": datetime.utcnow().isoformat()}


# ═══════════════════════════════════════════════════════════════════════════════
# POMODORO
# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/pomodoro/start", response_model=PomodoroOut)
def start_pomodoro(body: PomodoroStart, db: Session = Depends(get_db)):
    active = db.query(PomodoroSession).filter(PomodoroSession.completed == False).order_by(PomodoroSession.started_at.desc()).first()
    if active:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A Pomodoro session is already running for '{active.task_title or 'Pomodoro session'}'. "
                "Complete it before starting a new one."
            ),
        )

    session = PomodoroSession(
        task_id=body.task_id,
        task_title=body.task_title,
        duration_min=body.duration_min,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return {
        "session_id": session.id,
        "task_title": session.task_title,
        "duration_min": session.duration_min,
        "started_at": session.started_at,
    }


@router.post("/pomodoro/{session_id}/complete")
def complete_pomodoro(session_id: int, db: Session = Depends(get_db)):
    session = db.query(PomodoroSession).filter(PomodoroSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Pomodoro session not found")
    session.ended_at = datetime.utcnow()
    session.completed = True
    db.commit()
    return {"message": "Pomodoro completed", "duration_min": session.duration_min}


@router.post("/pomodoro/{session_id}/pause")
def pause_pomodoro(session_id: int, db: Session = Depends(get_db)):
    session = db.query(PomodoroSession).filter(PomodoroSession.id == session_id, PomodoroSession.completed == False).first()
    if not session:
        raise HTTPException(status_code=404, detail="Active Pomodoro session not found")
    if session.paused_at:
        raise HTTPException(status_code=400, detail="Session already paused")
    session.paused_at = datetime.utcnow()
    db.commit()
    return {"message": "Pomodoro paused", "paused_at": session.paused_at.isoformat()}


@router.post("/pomodoro/{session_id}/resume")
def resume_pomodoro(session_id: int, db: Session = Depends(get_db)):
    session = db.query(PomodoroSession).filter(PomodoroSession.id == session_id, PomodoroSession.completed == False).first()
    if not session:
        raise HTTPException(status_code=404, detail="Active Pomodoro session not found")
    if not session.paused_at:
        raise HTTPException(status_code=400, detail="Session is not paused")
    paused_duration = int((datetime.utcnow() - session.paused_at).total_seconds())
    session.paused_secs = (session.paused_secs or 0) + paused_duration
    session.paused_at = None
    db.commit()
    return {"message": "Pomodoro resumed", "paused_secs_total": session.paused_secs}


@router.get("/pomodoro/history")
def pomodoro_history(db: Session = Depends(get_db)):
    sessions = db.query(PomodoroSession).filter(PomodoroSession.completed == True).order_by(PomodoroSession.ended_at.desc()).limit(20).all()
    return [
        {
            "id": s.id,
            "task_title": s.task_title,
            "duration_min": s.duration_min,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "ended_at": s.ended_at.isoformat() if s.ended_at else None,
            "paused_secs": s.paused_secs or 0,
        }
        for s in sessions
    ]


@router.get("/pomodoro/active", response_model=PomodoroOut)
def get_active_pomodoro(db: Session = Depends(get_db)):
    session = db.query(PomodoroSession).filter(PomodoroSession.completed == False).order_by(PomodoroSession.started_at.desc()).first()
    if not session:
        raise HTTPException(status_code=404, detail="No active Pomodoro session")
    return {
        "session_id": session.id,
        "task_title": session.task_title,
        "duration_min": session.duration_min,
        "started_at": session.started_at,
        "paused_secs": session.paused_secs or 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ASSISTANT MODE
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/mode")
def get_mode(session_id: str = Query("default")):
    return mode_service.get_status(session_id)


@router.post("/mode")
def set_mode(body: ModeSet):
    sid = body.session_id or "default"
    intro = mode_service.set_mode(sid, body.mode)
    queued = mode_service.flush_dnd_queue(sid) if body.mode != "dnd" else []
    return {"mode": body.mode, "session_id": sid, "message": intro, "dnd_released": queued}
