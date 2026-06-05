"""
Intent Executor — takes parsed intent JSON, writes to DB, returns action summary.
This is the brain that maps LLM output → real data operations.
"""
import json
import re
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models.models import Sheet, Task, Meeting, Reminder, PomodoroSession, Note
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
        now = datetime.utcnow()
        if dt < now and dt.date() == now.date():
            dt += timedelta(days=1)
        return dt
    except Exception:
        return None


def _parse_duration_min(transcript: str, explicit_duration: int | None) -> int:
    if explicit_duration:
        try:
            return int(explicit_duration)
        except Exception:
            pass
    match = re.search(r"(\d+)\s*(?:min(?:ute)?s?|mins?)\b", transcript, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 25


def _is_note_command(transcript: str, entities: dict) -> bool:
    if entities.get("title") or entities.get("remarks"):
        return bool(re.search(r"\b(note|notes|notebook|remember this|jot down|write down)\b", transcript, re.IGNORECASE))
    return bool(re.search(r"\b(note|notes|notebook|remember this|jot down|write down)\b", transcript, re.IGNORECASE))


def _is_timer_command(transcript: str, entities: dict) -> bool:
    return bool(re.search(r"\b(timer|pomodoro|countdown|start.*timer|set.*timer)\b", transcript, re.IGNORECASE))


def _get_active_pomodoro(db: Session) -> PomodoroSession | None:
    return db.query(PomodoroSession).filter(PomodoroSession.completed == False).order_by(PomodoroSession.started_at.desc()).first()


def _create_note(db: Session, title: str | None, content: str | None) -> Note:
    note = Note(
        title=title or (content[:50] if content else "Untitled note"),
        content=content or title or "",
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def _result(summary: str, follow_up: str | None = None, debug_steps: list[str] | None = None) -> tuple[str, str | None, list[str] | None]:
    return summary, follow_up, debug_steps


def _dynamic_fallback(intent_data: dict, transcript: str, db: Session, sheet_name: str | None, title: str | None, priority: str | None, remarks: str | None, duration: int) -> tuple[str, str | None, list[str] | None] | None:
    debug_steps: list[str] = []
    if _is_note_command(transcript, intent_data.get("entities", {})):
        debug_steps.append("Detected a note-taking command")
        note = _create_note(db, title, remarks or transcript)
        debug_steps.append("Created new NOTE_CREATE skill and saved the note")
        summary = f"Saved a note titled '{note.title}'."
        return _result(summary, None, debug_steps)

    if _is_timer_command(transcript, intent_data.get("entities", {})):
        debug_steps.append("Detected a timer command")
        active = _get_active_pomodoro(db)
        if active:
            debug_steps.append("Found existing active Pomodoro session")
            return _result(
                f"A Pomodoro session is already running for '{active.task_title or 'Pomodoro session'}'. Complete it before starting another one.",
                "Would you like me to complete the current session first?",
                debug_steps,
            )
        resolved_duration = _parse_duration_min(transcript, duration)
        if title:
            task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first()
        else:
            task = None
        if not task and title:
            sheet = _resolve_sheet(db, sheet_name)
            if not sheet:
                sheet = db.query(Sheet).first()
            if sheet:
                task = Task(
                    sheet_id=sheet.id,
                    title=title,
                    status="in_progress",
                    priority=priority or "normal",
                    remarks=remarks,
                )
                db.add(task)
                db.commit()
                db.refresh(task)
                debug_steps.append("Created a supporting task for timer command")
        if task and task.status != "in_progress":
            task.status = "in_progress"
            task.synced = False
            db.commit()
            debug_steps.append("Updated task status to in_progress")
        session = PomodoroSession(
            task_id=task.id if task else None,
            task_title=title or (task.title if task else "Pomodoro session"),
            duration_min=resolved_duration,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        debug_steps.append("Created Pomodoro session")
        summary = f"Started a {session.duration_min}-minute Pomodoro session for '{session.task_title}'."
        return _result(summary, intent_data.get("suggested_followups", [None])[0], debug_steps)

    return None


async def execute(intent_data: dict, db: Session, transcript: str | None = None) -> tuple[str, str | None, list[str] | None]:
    """
    Execute the intent. Returns (action_summary, follow_up_question, debug_steps).
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
    columns   = entities.get("columns")
    raw_text  = transcript or ""

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
        return _result(f"Added task '{task.title}' to {sheet_str}{due_str}.", follow_up)

    # ── DELETE_TASK ───────────────────────────────────────────────────────────
    elif intent == "DELETE_TASK":
        task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first()
        if task:
            db.delete(task)
            db.commit()
            return _result(f"Deleted task '{task.title}'.")
        return _result("I couldn't find that task.")

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
            return _result(f"Updated task '{task.title}'.", follow_up)
        return _result("I couldn't find that task to update.")

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
            return _result("No tasks found matching your request.")
        items = "; ".join(
            f"{t.title} ({t.status}" + (f", due {t.due_date.strftime('%b %d')}" if t.due_date else "") + ")"
            for t in tasks
        )
        return _result(f"Found {len(tasks)} task(s): {items}.")

    # ── UPDATE_MEETING ────────────────────────────────────────────────────────
    elif intent == "UPDATE_MEETING":
        meeting = db.query(Meeting).filter(Meeting.title.ilike(f"%{title}%")).first()
        if meeting:
            if due_date: meeting.meeting_date = due_date
            if remarks:  meeting.remarks = remarks
            if participants:
                meeting.participants = json.dumps(participants) if isinstance(participants, list) else participants
            if entities.get("location"): meeting.location = entities["location"]
            meeting.synced = False
            db.commit()
            return _result(f"Updated meeting '{meeting.title}'.", follow_up)
        return _result("I couldn't find that meeting to update.")

    # ── QUERY_MEETINGS ────────────────────────────────────────────────────────
    elif intent == "QUERY_MEETINGS":
        q = db.query(Meeting)
        if sheet_name:
            sheet = _resolve_sheet(db, sheet_name)
            if sheet:
                q = q.filter(Meeting.sheet_id == sheet.id)
        meetings = q.order_by(Meeting.meeting_date.asc().nullslast()).limit(5).all()
        if not meetings:
            return _result("No meetings found.")
        items = "; ".join(
            f"{m.title}" + (f" on {m.meeting_date.strftime('%b %d at %I:%M %p')}" if m.meeting_date else "")
            for m in meetings
        )
        return _result(f"Found {len(meetings)} meeting(s): {items}.")

    # ── DELETE_MEETING ────────────────────────────────────────────────────────
    elif intent == "DELETE_MEETING":
        meeting = db.query(Meeting).filter(Meeting.title.ilike(f"%{title}%")).first()
        if meeting:
            db.delete(meeting)
            db.commit()
            return _result(f"Deleted meeting '{meeting.title}'.")
        return _result("I couldn't find that meeting.")

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
        return _result(f"Scheduled '{meeting.title}' on {date_str} in {sheet.name if sheet else 'default'} sheet.", follow_up)

    # ── NEW_SHEET ─────────────────────────────────────────────────────────────
    elif intent == "NEW_SHEET":
        name = title or sheet_name or "New Sheet"
        existing = db.query(Sheet).filter(Sheet.name.ilike(name)).first()
        if existing:
            return _result(f"A sheet named '{name}' already exists.")
        sheet = Sheet(
            name=name,
            tab_name=name,
            custom_columns=columns if isinstance(columns, list) else None,
        )
        db.add(sheet)
        db.commit()
        return _result(f"Created new sheet '{name}'.")

    # ── LIST_SHEETS ───────────────────────────────────────────────────────────
    elif intent == "LIST_SHEETS":
        sheets = db.query(Sheet).all()
        names = ", ".join(s.name for s in sheets)
        return _result(f"Your sheets are: {names}.")

    # ── SET_REMINDER ──────────────────────────────────────────────────────────
    elif intent == "SET_REMINDER":
        remind_at = due_date or (datetime.utcnow() + timedelta(minutes=30))
        task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first() if title else None
        reminder = Reminder(
            task_id=task.id if task else None,
            remind_at=remind_at,
            message=title or remarks or "Reminder",
        )
        db.add(reminder)
        db.commit()
        time_str = remind_at.strftime("%A %b %d at %I:%M %p")
        return _result(f"Reminder set for {time_str}.")

    # ── UPDATE_REMINDER ───────────────────────────────────────────────────────
    elif intent == "UPDATE_REMINDER":
        from app.models.models import Reminder as ReminderModel
        query_msg = title or remarks
        reminder = None
        if query_msg:
            reminder = db.query(ReminderModel).filter(ReminderModel.message.ilike(f"%{query_msg}%"), ReminderModel.delivered == False).first()
        if not reminder:
            reminder = db.query(ReminderModel).filter(ReminderModel.delivered == False).order_by(ReminderModel.remind_at.asc()).first()
        if reminder:
            if due_date: reminder.remind_at = due_date
            if remarks and remarks != title: reminder.message = remarks
            db.commit()
            time_str = reminder.remind_at.strftime("%A %b %d at %I:%M %p")
            return _result(f"Reminder updated to {time_str}.")
        return _result("I couldn't find that reminder to update.")

    # ── DELETE_REMINDER ───────────────────────────────────────────────────────
    elif intent == "DELETE_REMINDER":
        from app.models.models import Reminder as ReminderModel
        query_msg = title or remarks
        reminder = None
        if query_msg:
            reminder = db.query(ReminderModel).filter(ReminderModel.message.ilike(f"%{query_msg}%"), ReminderModel.delivered == False).first()
        if not reminder:
            if due_date:
                reminder = db.query(ReminderModel).filter(ReminderModel.remind_at >= due_date, ReminderModel.delivered == False).first()
        if reminder:
            db.delete(reminder)
            db.commit()
            return _result(f"Deleted reminder: '{reminder.message}'.")
        return _result("I couldn't find that reminder.")

    # ── NOTE_CREATE ───────────────────────────────────────────────────────────
    elif intent == "NOTE_CREATE":
        note = _create_note(db, title, remarks or raw_text)
        return _result(f"Note saved: '{note.title}'.", follow_up)

    # ── NOTE_READ / QUERY_NOTES ───────────────────────────────────────────────
    elif intent in ("NOTE_READ", "QUERY_NOTES"):
        q = db.query(Note)
        if title:
            q = q.filter(Note.title.ilike(f"%{title}%") | Note.content.ilike(f"%{title}%"))
        notes = q.order_by(Note.created_at.desc()).limit(5).all()
        if not notes:
            return _result("No notes found.")
        items = "; ".join(f"'{n.title}'" for n in notes)
        return _result(f"Found {len(notes)} note(s): {items}.")

    # ── NOTE_UPDATE ───────────────────────────────────────────────────────────
    elif intent == "NOTE_UPDATE":
        note = db.query(Note).filter(Note.title.ilike(f"%{title}%")).first()
        if note:
            if remarks: note.content = remarks
            if entities.get("new_title"): note.title = entities["new_title"]
            db.commit()
            return _result(f"Updated note '{note.title}'.")
        return _result("I couldn't find that note to update.")

    # ── NOTE_DELETE ───────────────────────────────────────────────────────────
    elif intent == "NOTE_DELETE":
        note = db.query(Note).filter(Note.title.ilike(f"%{title}%")).first()
        if note:
            db.delete(note)
            db.commit()
            return _result(f"Deleted note '{note.title}'.")
        return _result("I couldn't find that note.")

    # ── POMODORO_PAUSE ────────────────────────────────────────────────────────
    elif intent == "POMODORO_PAUSE":
        active = _get_active_pomodoro(db)
        if active:
            if active.paused_at:
                return _result("Pomodoro already paused. Say 'resume timer' to continue.")
            active.paused_at = datetime.utcnow()
            db.commit()
            return _result(f"Paused Pomodoro for '{active.task_title}'.")
        return _result("No active Pomodoro session to pause.")

    # ── POMODORO_RESUME ───────────────────────────────────────────────────────
    elif intent == "POMODORO_RESUME":
        active = _get_active_pomodoro(db)
        if active and active.paused_at:
            paused_duration = int((datetime.utcnow() - active.paused_at).total_seconds())
            active.paused_secs = (active.paused_secs or 0) + paused_duration
            active.paused_at = None
            db.commit()
            return _result(f"Resumed Pomodoro for '{active.task_title}'.")
        return _result("No paused Pomodoro session found.")

    # ── POMODORO_STOP ─────────────────────────────────────────────────────────
    elif intent == "POMODORO_STOP":
        active = _get_active_pomodoro(db)
        if active:
            active.ended_at = datetime.utcnow()
            active.completed = True
            db.commit()
            return _result(f"Stopped Pomodoro session for '{active.task_title}'.")
        return _result("No active Pomodoro session.")

    # ── SET_MODE ──────────────────────────────────────────────────────────────
    elif intent == "SET_MODE":
        mode = entities.get("mode", "chat").lower()
        valid_modes = {"focus", "briefing", "research", "chat", "dnd"}
        if mode not in valid_modes:
            return _result(f"Unknown mode '{mode}'. Available: {', '.join(sorted(valid_modes))}.")
        mode_descriptions = {
            "focus": "Focus mode — Pomodoro tracking, minimal distractions, task-only queries.",
            "briefing": "Briefing mode — I'll proactively summarize your day and upcoming events.",
            "research": "Research mode — web search results are automatically saved as notes.",
            "chat": "Chat mode — casual conversation, no productivity enforcement.",
            "dnd": "Do Not Disturb — reminders muted and queued for later.",
        }
        return _result(f"Switched to {mode.upper()} mode. {mode_descriptions.get(mode, '')}", follow_up, [f"mode:{mode}"])

    # ── SWITCH_SHEET ──────────────────────────────────────────────────────────
    elif intent == "SWITCH_SHEET":
        sheet = _resolve_sheet(db, sheet_name or title)
        if sheet:
            return _result(f"Switched to sheet '{sheet.name}'.", follow_up)
        return _result(f"Sheet '{sheet_name or title}' not found.")

    # ── DELETE_SHEET ──────────────────────────────────────────────────────────
    elif intent == "DELETE_SHEET":
        sheet = _resolve_sheet(db, sheet_name or title)
        if sheet:
            db.delete(sheet)
            db.commit()
            return _result(f"Deleted sheet '{sheet.name}' and all its tasks and meetings.")
        return _result("I couldn't find that sheet to delete.")

    # ── POMODORO_START ─────────────────────────────────────────────────────────
    elif intent == "POMODORO_START":
        active = _get_active_pomodoro(db)
        if active:
            return _result(
                f"A Pomodoro session is already running for '{active.task_title or 'Pomodoro session'}'. Complete it before starting another one.",
                "Would you like me to complete the current session first?",
                ["Found existing active Pomodoro session"],
            )
        task = None
        if title:
            task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first()
            if not task:
                sheet = _resolve_sheet(db, sheet_name)
                if not sheet:
                    sheet = db.query(Sheet).first()
                if sheet:
                    task = Task(
                        sheet_id=sheet.id,
                        title=title,
                        status="in_progress",
                        priority=priority or "normal",
                        remarks=remarks,
                    )
                    db.add(task)
                    db.commit()
                    db.refresh(task)
            else:
                if task.status != "in_progress":
                    task.status = "in_progress"
                    task.synced = False
                    db.commit()
        session = PomodoroSession(
            task_id=task.id if task else None,
            task_title=title or (task.title if task else "Pomodoro session"),
            duration_min=duration or 25,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return _result(f"Started a {session.duration_min}-minute Pomodoro session for '{session.task_title}'.", follow_up)

    # ── MORNING_BRIEFING ──────────────────────────────────────────────────────────────
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
        return _result(f"Good morning! Here's your day: {summary}.")

    # ── SYNC_NOW ──────────────────────────────────────────────────────────────
    elif intent == "SYNC_NOW":
        return _result("Syncing your data to Google Sheets now.")

    # ── WEB_SEARCH ────────────────────────────────────────────────────────────
    elif intent == "WEB_SEARCH":
        search_query = remarks or title or raw_text
        if not search_query:
            return _result("I couldn't find a search query in your request.")
        
        from app.services.search_service import search_service
        try:
            results = await search_service.search(search_query, max_results=3)
            if not results:
                return _result(f"I searched the web for '{search_query}' but couldn't find any relevant results.")
            
            # Format the search results as a summary for the LLM to read and synthesize response
            summary_parts = [f"Web search results for '{search_query}':"]
            for idx, r in enumerate(results, 1):
                summary_parts.append(f"[{idx}] Title: {r['title']}\nSnippet: {r['body']}\nSource: {r['href']}")
            
            summary = "\n\n".join(summary_parts)
            return _result(summary)
        except Exception as e:
            logger.error(f"Intent executor web search error: {e}")
            return _result(f"Sorry, I encountered an error while searching the web for '{search_query}'.")

    # ── CHAT ──────────────────────────────────────────────────────────────────
    elif intent == "CHAT":
        return _result(None, None, None)

    # ── UNKNOWN ───────────────────────────────────────────────────────────────
    else:
        dynamic = _dynamic_fallback(intent_data, raw_text, db, sheet_name, title, priority, remarks, duration)
        if dynamic:
            return dynamic
        return _result(None, None, None)
