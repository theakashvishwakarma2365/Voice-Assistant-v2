"""
Assistant Mode Service — tracks active mode per session and applies mode-aware
behaviour to the intent pipeline.

Modes:
  focus     — only task/timer/reminder intents pass; blocks chat/search
  briefing  — on connect, auto-fires MORNING_BRIEFING; responds proactively
  research  — WEB_SEARCH results are auto-saved as notes
  chat      — default; no restrictions
  dnd       — reminders muted and queued; non-urgent intents still execute
"""
from datetime import datetime
from typing import Optional

_WRITE_INTENTS = {
    "ADD_TASK", "DELETE_TASK", "UPDATE_TASK",
    "SCHEDULE_MEETING", "DELETE_MEETING", "UPDATE_MEETING",
    "NEW_SHEET", "DELETE_SHEET", "SET_REMINDER", "DELETE_REMINDER",
    "UPDATE_REMINDER", "SYNC_NOW", "NOTE_CREATE", "NOTE_DELETE",
    "NOTE_UPDATE", "POMODORO_START", "POMODORO_STOP", "POMODORO_PAUSE",
    "POMODORO_RESUME",
}

_FOCUS_ALLOWED = {
    "ADD_TASK", "DELETE_TASK", "UPDATE_TASK", "QUERY_TASKS",
    "POMODORO_START", "POMODORO_STOP", "POMODORO_PAUSE", "POMODORO_RESUME",
    "SET_REMINDER", "DELETE_REMINDER", "UPDATE_REMINDER",
    "MORNING_BRIEFING", "SYNC_NOW", "SET_MODE",
}

_MODE_INTRO = {
    "focus":    "Focus mode activated. I'll only handle tasks and timers.",
    "briefing": "Briefing mode on. I'll keep you updated on your day.",
    "research": "Research mode on. Search results will be saved as notes.",
    "chat":     "Chat mode on. Ask me anything!",
    "dnd":      "Do Not Disturb activated. Reminders are queued.",
}


class ModeService:
    def __init__(self):
        self._modes: dict[str, str] = {}
        self._mode_since: dict[str, datetime] = {}
        self._dnd_queue: dict[str, list[str]] = {}

    def get_mode(self, session_id: str) -> str:
        return self._modes.get(session_id, "chat")

    def set_mode(self, session_id: str, mode: str) -> str:
        self._modes[session_id] = mode
        self._mode_since[session_id] = datetime.utcnow()
        return _MODE_INTRO.get(mode, f"Mode set to {mode}.")

    def get_mode_intro(self, mode: str) -> str:
        return _MODE_INTRO.get(mode, "")

    def is_intent_allowed(self, session_id: str, intent: str) -> bool:
        mode = self.get_mode(session_id)
        if mode == "focus":
            return intent in _FOCUS_ALLOWED
        return True

    def get_blocked_message(self, session_id: str, intent: str) -> str:
        mode = self.get_mode(session_id)
        if mode == "focus":
            return "Focus mode is active. I'm only handling tasks and timers right now. Say 'chat mode' to switch."
        return "This action is restricted in the current mode."

    def should_auto_briefing(self, session_id: str) -> bool:
        return self.get_mode(session_id) == "briefing"

    def should_save_search_as_note(self, session_id: str) -> bool:
        return self.get_mode(session_id) == "research"

    def is_dnd(self, session_id: str) -> bool:
        return self.get_mode(session_id) == "dnd"

    def queue_dnd_reminder(self, session_id: str, message: str):
        if session_id not in self._dnd_queue:
            self._dnd_queue[session_id] = []
        self._dnd_queue[session_id].append(message)

    def flush_dnd_queue(self, session_id: str) -> list[str]:
        return self._dnd_queue.pop(session_id, [])

    def get_status(self, session_id: str) -> dict:
        mode = self.get_mode(session_id)
        since = self._mode_since.get(session_id)
        queued = len(self._dnd_queue.get(session_id, []))
        return {
            "mode": mode,
            "since": since.isoformat() if since else None,
            "dnd_queued": queued,
        }


mode_service = ModeService()
