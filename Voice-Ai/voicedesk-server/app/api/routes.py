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
from app.models.models import Sheet, Task, Meeting, Reminder, PomodoroSession
from app.models.schemas import (
    SheetCreate, SheetOut,
    TaskCreate, TaskUpdate, TaskOut,
    MeetingCreate, MeetingOut,
    ReminderCreate, ReminderOut,
    PomodoroStart, PomodoroOut,
    OfflineBatch, ServerStatus,
)
from app.services.sheets_service import sheets_service
from app.services.stt_service import stt_service
from app.services.llm_service import llm_service
from app.services.tts_service import tts_service
from app.core.config import settings
from app.core.logger import logger

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
    sheet = Sheet(name=body.name, tab_name=body.name, color_tag=body.color_tag)
    db.add(sheet)
    db.commit()
    db.refresh(sheet)
    sheets_service.ensure_tab_exists(sheet.name)
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
    sheets_service.sync_all(db)
    logger.info(f"Offline batch: {processed} processed, {errors} errors")
    return {"processed": processed, "errors": errors}


# ═══════════════════════════════════════════════════════════════════════════════
# SYNC
# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/sync")
def force_sync(db: Session = Depends(get_db)):
    sheets_service.sync_all(db)
    return {"message": "Sync triggered", "timestamp": datetime.utcnow().isoformat()}


# ═══════════════════════════════════════════════════════════════════════════════
# POMODORO
# ═══════════════════════════════════════════════════════════════════════════════
@router.post("/pomodoro/start", response_model=PomodoroOut)
def start_pomodoro(body: PomodoroStart, db: Session = Depends(get_db)):
    session = PomodoroSession(
        task_id=body.task_id,
        task_title=body.task_title,
        duration_min=body.duration_min,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.post("/pomodoro/{session_id}/complete")
def complete_pomodoro(session_id: int, db: Session = Depends(get_db)):
    session = db.query(PomodoroSession).filter(PomodoroSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Pomodoro session not found")
    session.ended_at = datetime.utcnow()
    session.completed = True
    db.commit()
    return {"message": "Pomodoro completed", "duration_min": session.duration_min}
