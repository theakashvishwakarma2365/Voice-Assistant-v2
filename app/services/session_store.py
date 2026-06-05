"""
Session store service — tracks conversation history and pending confirmations
across WebSocket and REST API sessions using session IDs.
"""
from typing import Any
from sqlalchemy.orm import Session
from app.models.models import Sheet, CommandLog
from app.services.llm_service import llm_service
from app.services import intent_executor
from app.core.logger import logger

_AFFIRMATIVE = {"yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "please", "do it", "yup", "of course", "absolutely"}
_NEGATIVE = {"no", "nope", "cancel", "nevermind", "never mind", "don't", "stop", "skip"}

def is_affirmative(text: str) -> bool:
    return text.strip().lower().rstrip(".?!") in _AFFIRMATIVE

def is_negative(text: str) -> bool:
    return text.strip().lower().rstrip(".?!") in _NEGATIVE


class SessionStore:
    def __init__(self):
        self._pending_confirmations: dict[str, dict] = {}
        self._conversation_histories: dict[str, list[dict[str, str]]] = {}

    def get_history(self, session_id: str) -> list[dict[str, str]]:
        if session_id not in self._conversation_histories:
            self._conversation_histories[session_id] = []
        return self._conversation_histories[session_id]

    def set_history(self, session_id: str, history: list[dict[str, str]]):
        self._conversation_histories[session_id] = history[-10:]

    def add_message(self, session_id: str, role: str, content: str):
        history = self.get_history(session_id)
        history.append({"role": role, "content": content})
        self._conversation_histories[session_id] = history[-10:]

    def get_pending(self, session_id: str) -> dict:
        return self._pending_confirmations.get(session_id, {})

    def set_pending(self, session_id: str, pending_data: dict):
        self._pending_confirmations[session_id] = pending_data

    def pop_pending(self, session_id: str) -> dict:
        return self._pending_confirmations.pop(session_id, {})


session_store = SessionStore()


async def resolve_confirmation_action(
    session_id: str,
    transcript: str,
    db: Session,
    accepted: bool
) -> dict:
    """
    Resolves the pending confirmation for a session_id.
    Returns a dict with execution details:
      {
        "intent": str,
        "action_summary": str,
        "response_text": str,
        "follow_up": str | None,
        "debug_steps": list | None,
        "sheets_sync": bool
      }
    """
    pending = session_store.pop_pending(session_id)
    if not pending:
        return {}

    follow_up_text = pending.get("follow_up", "")
    search_summary = pending.get("search_summary", "")
    search_query = pending.get("search_query", "")

    if not accepted:
        response_text = "Alright, no problem! What else can I help you with?"
        session_store.add_message(session_id, "user", transcript)
        session_store.add_message(session_id, "assistant", response_text)
        return {
            "intent": "CHAT",
            "action_summary": response_text,
            "response_text": response_text,
            "follow_up": None,
            "debug_steps": None,
            "sheets_sync": False,
            "entities": {}
        }

    # Accepted! Determine what was being confirmed from the follow-up text
    sheets = db.query(Sheet).all()
    sheet_names = [s.name for s in sheets]
    history = session_store.get_history(session_id)

    # Build a chained instruction: "yes, go ahead and [follow_up]"
    chained_prompt = (
        f"The user confirmed: '{follow_up_text}'. "
        f"Context from previous search results: {search_summary[:500]}. "
        f"Original search query was: '{search_query}'. "
        f"Execute the appropriate action now."
    )

    chained_intent = await llm_service.parse_intent(chained_prompt, sheet_names, history)
    chained_intent_name = chained_intent.get("intent", "UNKNOWN")

    action_summary, new_follow_up, debug_steps = await intent_executor.execute(
        chained_intent, db, chained_prompt
    )

    if action_summary is None:
        response_text = await llm_service.generate_chat_response(
            f"User confirmed: {follow_up_text}", history, context=search_summary
        )
    elif chained_intent_name == "WEB_SEARCH":
        response_text = await llm_service.generate_response(action_summary, new_follow_up)
    else:
        response_text = action_summary
        if new_follow_up:
            response_text += f" {new_follow_up}"

    session_store.add_message(session_id, "user", transcript)
    session_store.add_message(session_id, "assistant", response_text)

    _WRITE_INTENTS = {
        "ADD_TASK", "DELETE_TASK", "UPDATE_TASK",
        "SCHEDULE_MEETING", "DELETE_MEETING",
        "NEW_SHEET", "DELETE_SHEET", "SET_REMINDER", "SYNC_NOW",
    }
    sheets_sync = chained_intent_name in _WRITE_INTENTS

    return {
        "intent": chained_intent_name,
        "action_summary": action_summary or response_text,
        "response_text": response_text,
        "follow_up": new_follow_up,
        "debug_steps": debug_steps,
        "sheets_sync": sheets_sync,
        "entities": chained_intent.get("entities", {})
    }
