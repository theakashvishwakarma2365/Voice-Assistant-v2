"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


# ── Sheet ─────────────────────────────────────────────────────────────────────
class SheetCreate(BaseModel):
    name: str
    color_tag: Optional[str] = "#0F3C78"

class SheetOut(BaseModel):
    id: int
    name: str
    color_tag: Optional[str]
    created_at: datetime
    last_synced: Optional[datetime]
    model_config = {"from_attributes": True}


# ── Task ──────────────────────────────────────────────────────────────────────
class TaskCreate(BaseModel):
    sheet_id: int
    title: str
    status: str = "pending"
    due_date: Optional[datetime] = None
    priority: str = "normal"
    remarks: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = None
    remarks: Optional[str] = None

class TaskOut(BaseModel):
    id: int
    sheet_id: int
    title: str
    status: str
    due_date: Optional[datetime]
    priority: str
    remarks: Optional[str]
    created_at: datetime
    updated_at: datetime
    synced: bool
    model_config = {"from_attributes": True}


# ── Meeting ───────────────────────────────────────────────────────────────────
class MeetingCreate(BaseModel):
    sheet_id: int
    title: str
    meeting_date: Optional[datetime] = None
    participants: Optional[str] = None
    location: Optional[str] = None
    remarks: Optional[str] = None
    renewal_date: Optional[datetime] = None
    renewal_note: Optional[str] = None

class MeetingOut(BaseModel):
    id: int
    sheet_id: int
    title: str
    meeting_date: Optional[datetime]
    participants: Optional[str]
    location: Optional[str]
    remarks: Optional[str]
    renewal_date: Optional[datetime]
    renewal_note: Optional[str]
    created_at: datetime
    synced: bool
    model_config = {"from_attributes": True}


# ── Reminder ──────────────────────────────────────────────────────────────────
class ReminderCreate(BaseModel):
    task_id: Optional[int] = None
    meeting_id: Optional[int] = None
    remind_at: datetime
    message: Optional[str] = None

class ReminderOut(BaseModel):
    id: int
    task_id: Optional[int]
    meeting_id: Optional[int]
    remind_at: datetime
    message: Optional[str]
    delivered: bool
    model_config = {"from_attributes": True}


# ── Voice / WebSocket ─────────────────────────────────────────────────────────
class VoiceResponse(BaseModel):
    transcript: str
    intent: str
    confidence: float
    response_text: str
    audio_file: Optional[str] = None   # filename in audio_cache/
    display: Dict[str, Any] = {}
    follow_up: Optional[str] = None
    clarification_needed: Optional[str] = None
    action_taken: Optional[str] = None


class OfflineBatchItem(BaseModel):
    type: str           # "task" | "meeting" | "reminder"
    data: Dict[str, Any]
    queued_at: str      # ISO timestamp from ESP32

class OfflineBatch(BaseModel):
    items: List[OfflineBatchItem]
    device_id: Optional[str] = None


# ── Status ────────────────────────────────────────────────────────────────────
class ServerStatus(BaseModel):
    status: str
    uptime_seconds: float
    whisper_loaded: bool
    ollama_reachable: bool
    sheets_connected: bool
    db_ok: bool
    pending_reminders: int
    audio_cache_mb: float


# ── Pomodoro ──────────────────────────────────────────────────────────────────
class PomodoroStart(BaseModel):
    task_title: Optional[str] = None
    task_id: Optional[int] = None
    duration_min: int = 25

class PomodoroOut(BaseModel):
    session_id: int
    task_title: Optional[str]
    duration_min: int
    started_at: datetime
    model_config = {"from_attributes": True}
