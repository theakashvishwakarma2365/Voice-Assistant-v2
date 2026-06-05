"""
Intent Executor — takes parsed intent JSON, writes to DB, returns action summary.
This is the brain that maps LLM output → real data operations.
"""
import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import Sheet, Task, Meeting, Reminder
from app.core.logger import logger


def _resolve_sheet(db: Session, name: str | None) -> Sheet | None:
    if not name:
        return None
    return db.query(Sheet).filter(Sheet.name.ilike(f"%{name}%")).first()


def _parse_dt(date_str: str | None, time_str: str | None = None) -> datetime | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str)
        if time_str:
            h, m = map(int, time_str.split(":"))
            dt = dt.replace(hour=h, minute=m)
        return dt
    except Exception:
        return None


def execute(intent_data: dict, db: Session) -> tuple[str, str | None]:
    """
    Execute the intent. Returns (action_summary, follow_up_question).
    action_summary is fed to LLM for response generation.
    """
    intent   = intent_data.get("intent", "UNKNOWN")
    entities = intent_data.get("entities", {})
    followups = intent_data.get("suggested_followups", [])
    follow_up = followups[0] if followups else None

    title     = entities.get("title")
    sheet_name= entities.get("sheet")
    due_date  = _parse_dt(entities.get("due_date"), entities.get("time"))
    priority  = entities.get("priority", "normal")
    remarks   = entities.get("remarks")
    status    = entities.get("status")
    participants = entities.get("participants")
    duration  = entities.get("duration_min", 25)

    # ── ADD_TASK ──────────────────────────────────────────────────────────────
    if intent == "ADD_TASK":
        sheet = _resolve_sheet(db, sheet_name)
        if not sheet:
            sheet = db.query(Sheet).first()  # fallback to first sheet
        task = Task(
            sheet_id=sheet.id if sheet else 1,
            title=title or "Untitled task",
            status="pending",
            due_date=due_date,
            priority=priority or "normal",
            remarks=remarks,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        due_str = f" due {due_date.strftime('%A %b %d')}" if due_date else ""
        sheet_str = sheet.name if sheet else "default"
        return (f"Added task '{task.title}' to {sheet_str}{due_str}.", follow_up)

    # ── DELETE_TASK ───────────────────────────────────────────────────────────
    elif intent == "DELETE_TASK":
        task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first()
        if task:
            db.delete(task)
            db.commit()
            return (f"Deleted task '{task.title}'.", None)
        return ("I couldn't find that task.", None)

    # ── UPDATE_TASK ───────────────────────────────────────────────────────────
    elif intent == "UPDATE_TASK":
        task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first()
        if task:
            if status:   task.status   = status
            if due_date: task.due_date = due_date
            if remarks:  task.remarks  = remarks
            if priority: task.priority = priority
            task.synced = False
            db.commit()
            return (f"Updated task '{task.title}'.", follow_up)
        return ("I couldn't find that task to update.", None)

    # ── QUERY_TASKS ───────────────────────────────────────────────────────────
    elif intent == "QUERY_TASKS":
        q = db.query(Task)
        if sheet_name:
            sheet = _resolve_sheet(db, sheet_name)
            if sheet:
                q = q.filter(Task.sheet_id == sheet.id)
        if status:
            q = q.filter(Task.status == status)
        else:
            q = q.filter(Task.status != "done")
        tasks = q.order_by(Task.due_date.asc().nullslast()).limit(5).all()
        if not tasks:
            return ("No tasks found matching your request.", None)
        items = "; ".join(
            f"{t.title} ({t.status}" + (f", due {t.due_date.strftime('%b %d')}" if t.due_date else "") + ")"
            for t in tasks
        )
        return (f"Found {len(tasks)} task(s): {items}.", None)

    # ── SCHEDULE_MEETING ──────────────────────────────────────────────────────
    elif intent == "SCHEDULE_MEETING":
        sheet = _resolve_sheet(db, sheet_name)
        if not sheet:
            sheet = db.query(Sheet).first()
        meeting = Meeting(
            sheet_id=sheet.id if sheet else 1,
            title=title or "Untitled meeting",
            meeting_date=due_date,
            participants=json.dumps(participants) if isinstance(participants, list) else participants,
            remarks=remarks,
        )
        db.add(meeting)
        db.commit()
        db.refresh(meeting)
        date_str = due_date.strftime("%A %b %d at %I:%M %p") if due_date else "date TBD"
        return (f"Scheduled '{meeting.title}' on {date_str} in {sheet.name if sheet else 'default'} sheet.", follow_up)

    # ── NEW_SHEET ─────────────────────────────────────────────────────────────
    elif intent == "NEW_SHEET":
        name = title or sheet_name or "New Sheet"
        existing = db.query(Sheet).filter(Sheet.name.ilike(name)).first()
        if existing:
            return (f"A sheet named '{name}' already exists.", None)
        sheet = Sheet(name=name, tab_name=name)
        db.add(sheet)
        db.commit()
        return (f"Created new sheet '{name}'.", None)

    # ── LIST_SHEETS ───────────────────────────────────────────────────────────
    elif intent == "LIST_SHEETS":
        sheets = db.query(Sheet).all()
        names = ", ".join(s.name for s in sheets)
        return (f"Your sheets are: {names}.", None)

    # ── SET_REMINDER ──────────────────────────────────────────────────────────
    elif intent == "SET_REMINDER":
        remind_at = due_date or (datetime.utcnow() + timedelta(minutes=30))
        # Try to link to a task by title
        task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first() if title else None
        reminder = Reminder(
            task_id=task.id if task else None,
            remind_at=remind_at,
            message=title or remarks or "Reminder",
        )
        db.add(reminder)
        db.commit()
        time_str = remind_at.strftime("%A %b %d at %I:%M %p")
        return (f"Reminder set for {time_str}.", None)

    # ── MORNING_BRIEFING ──────────────────────────────────────────────────────
    elif intent == "MORNING_BRIEFING":
        today = datetime.utcnow().date()
        tasks = db.query(Task).filter(
            Task.status == "pending",
            Task.due_date >= datetime.utcnow(),
        ).order_by(Task.due_date.asc()).limit(3).all()
        overdue = db.query(Task).filter(
            Task.status == "pending",
            Task.due_date < datetime.utcnow(),
        ).count()
        meetings = db.query(Meeting).filter(
            Meeting.meeting_date >= datetime.utcnow(),
        ).order_by(Meeting.meeting_date.asc()).limit(2).all()

        parts = []
        if overdue:
            parts.append(f"{overdue} overdue task(s)")
        if tasks:
            parts.append(f"{len(tasks)} upcoming task(s), next: {tasks[0].title}")
        if meetings:
            parts.append(f"next meeting: {meetings[0].title}")
        summary = "; ".join(parts) if parts else "nothing scheduled"
        return (f"Good morning! Here's your day: {summary}.", None)

    # ── SYNC_NOW ──────────────────────────────────────────────────────────────
    elif intent == "SYNC_NOW":
        return ("Syncing your data to Google Sheets now.", None)

    # ── UNKNOWN ───────────────────────────────────────────────────────────────
    else:
        return ("I didn't quite understand that. Could you rephrase?", None)
