"""
LLM service — intent parsing + response generation via Ollama.
"""
import json
import httpx
from datetime import date
from typing import Any
from app.core.config import settings
from app.core.logger import logger

INTENT_SYSTEM_PROMPT = """You are VoiceDesk, a voice productivity assistant.
Your ONLY job is to extract structured data from user speech and return ONLY valid JSON.
Never add explanation or markdown outside the JSON.

Valid intents:
  ADD_TASK | DELETE_TASK | UPDATE_TASK | QUERY_TASKS |
  SCHEDULE_MEETING | DELETE_MEETING | QUERY_MEETINGS |
  NEW_SHEET | SWITCH_SHEET | DELETE_SHEET | LIST_SHEETS |
  SET_REMINDER | DELETE_REMINDER |
  POMODORO_START | POMODORO_STOP | POMODORO_PAUSE |
  MORNING_BRIEFING | SYNC_NOW | UNKNOWN

Output format (always return exactly this structure):
{
  "intent": "<INTENT>",
  "confidence": <0.0-1.0>,
  "entities": {
    "title": null,
    "sheet": null,
    "due_date": null,
    "time": null,
    "priority": null,
    "remarks": null,
    "participants": null,
    "duration_min": null,
    "status": null
  },
  "missing_fields": [],
  "clarification_needed": null,
  "suggested_followups": []
}

Rules:
- due_date must be ISO format YYYY-MM-DD. Resolve relative dates (today, tomorrow, next Monday).
- time must be HH:MM (24h).
- If a required field is missing, add it to missing_fields and put ONE question in clarification_needed.
- Suggest 1-2 smart follow-ups where relevant (e.g. "Set a reminder?", "Add renewal date?").
- Never guess a sheet name — if ambiguous, ask.
- Today's date: {today}
- Available sheets: {sheets}
"""

RESPONSE_SYSTEM_PROMPT = """You are VoiceDesk, a friendly voice assistant.
Generate a SHORT, natural spoken response (1-3 sentences max) confirming the action.
Do NOT use markdown. Speak as if talking out loud. Be concise and warm.
If a follow-up question was suggested, end with it naturally."""


class LLMService:
    def __init__(self):
        self._client = httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=30.0,
        )

    async def is_reachable(self) -> bool:
        try:
            r = await self._client.get("/api/tags")
            return r.status_code == 200
        except Exception:
            return False

    async def parse_intent(
        self,
        transcript: str,
        available_sheets: list[str],
    ) -> dict[str, Any]:
        """Parse user transcript into structured intent JSON."""
        system = INTENT_SYSTEM_PROMPT.format(
            today=date.today().isoformat(),
            sheets=", ".join(available_sheets) if available_sheets else "none yet",
        )
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user",   "content": transcript},
                    ],
                    "options": {"temperature": 0.1},
                },
            )
            content = response.json()["message"]["content"].strip()

            # Strip markdown code fences if model adds them
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            result = json.loads(content)
            logger.info(f"Intent: {result.get('intent')} (conf={result.get('confidence')})")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"LLM JSON parse error: {e} | raw: {content[:200]}")
            return {"intent": "UNKNOWN", "confidence": 0.0, "entities": {}, "missing_fields": [], "clarification_needed": None, "suggested_followups": []}
        except Exception as e:
            logger.error(f"LLM error: {e}")
            return {"intent": "UNKNOWN", "confidence": 0.0, "entities": {}, "missing_fields": [], "clarification_needed": None, "suggested_followups": []}

    async def generate_response(
        self,
        action_summary: str,
        follow_up: str | None = None,
    ) -> str:
        """Generate a natural spoken response for the completed action."""
        prompt = action_summary
        if follow_up:
            prompt += f"\nAlso ask: {follow_up}"
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
                        {"role": "user",   "content": prompt},
                    ],
                    "options": {"temperature": 0.7},
                },
            )
            text = response.json()["message"]["content"].strip()
            logger.info(f"LLM response: '{text[:80]}...'")
            return text
        except Exception as e:
            logger.error(f"LLM response error: {e}")
            return action_summary   # fallback to raw summary


# Singleton
llm_service = LLMService()
