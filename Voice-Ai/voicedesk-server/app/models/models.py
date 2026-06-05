"""
SQLAlchemy ORM models — full schema.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    Text, ForeignKey, Float
)
from sqlalchemy.orm import relationship
from app.models.database import Base


class Sheet(Base):
    __tablename__ = "sheets"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String(100), unique=True, nullable=False)
    google_sheet_id = Column(String(200), nullable=True)
    tab_name      = Column(String(100), nullable=True)
    color_tag     = Column(String(20), default="#0F3C78")
    created_at    = Column(DateTime, default=datetime.utcnow)
    last_synced   = Column(DateTime, nullable=True)

    tasks    = relationship("Task",    back_populates="sheet", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="sheet", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id         = Column(Integer, primary_key=True, index=True)
    sheet_id   = Column(Integer, ForeignKey("sheets.id"), nullable=False)
    title      = Column(String(300), nullable=False)
    status     = Column(String(20), default="pending")   # pending|in_progress|done|cancelled
    due_date   = Column(DateTime, nullable=True)
    priority   = Column(String(10), default="normal")    # low|normal|high|urgent
    remarks    = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced     = Column(Boolean, default=False)

    sheet     = relationship("Sheet", back_populates="tasks")
    reminders = relationship("Reminder", back_populates="task", cascade="all, delete-orphan")


class Meeting(Base):
    __tablename__ = "meetings"

    id            = Column(Integer, primary_key=True, index=True)
    sheet_id      = Column(Integer, ForeignKey("sheets.id"), nullable=False)
    title         = Column(String(300), nullable=False)
    meeting_date  = Column(DateTime, nullable=True)
    participants  = Column(Text, nullable=True)   # JSON array string
    location      = Column(String(200), nullable=True)
    remarks       = Column(Text, nullable=True)
    renewal_date  = Column(DateTime, nullable=True)
    renewal_note  = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    updated_at    = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced        = Column(Boolean, default=False)

    sheet     = relationship("Sheet", back_populates="meetings")
    reminders = relationship("Reminder", back_populates="meeting", cascade="all, delete-orphan")


class Reminder(Base):
    __tablename__ = "reminders"

    id         = Column(Integer, primary_key=True, index=True)
    task_id    = Column(Integer, ForeignKey("tasks.id"),    nullable=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"), nullable=True)
    remind_at  = Column(DateTime, nullable=False)
    message    = Column(Text, nullable=True)
    delivered  = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    task    = relationship("Task",    back_populates="reminders")
    meeting = relationship("Meeting", back_populates="reminders")


class CommandLog(Base):
    __tablename__ = "command_log"

    id            = Column(Integer, primary_key=True, index=True)
    transcript    = Column(Text, nullable=True)
    intent        = Column(String(50), nullable=True)
    entities_json = Column(Text, nullable=True)
    success       = Column(Boolean, default=True)
    response_text = Column(Text, nullable=True)
    latency_ms    = Column(Integer, nullable=True)
    created_at    = Column(DateTime, default=datetime.utcnow)


class PomodoroSession(Base):
    __tablename__ = "pomodoro_sessions"

    id          = Column(Integer, primary_key=True, index=True)
    task_id     = Column(Integer, ForeignKey("tasks.id"), nullable=True)
    task_title  = Column(String(300), nullable=True)
    duration_min = Column(Integer, default=25)
    started_at  = Column(DateTime, default=datetime.utcnow)
    ended_at    = Column(DateTime, nullable=True)
    completed   = Column(Boolean, default=False)
