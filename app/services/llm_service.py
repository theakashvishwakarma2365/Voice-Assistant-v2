"""
LLM service — intent parsing + response generation via Ollama.
"""
import json
import httpx
from datetime import date
from typing import Any
from app.core.config import settings
from app.core.logger import logger

INTENT_SYSTEM_PROMPT = """You are VoiceDesk, a voice productivity assistant intent classifier.
Your ONLY job is to extract structured data from user speech and return ONLY valid JSON.
Never add explanation or markdown outside the JSON block.

Valid intents:
  ADD_TASK | DELETE_TASK | UPDATE_TASK | QUERY_TASKS |
  SCHEDULE_MEETING | DELETE_MEETING | QUERY_MEETINGS |
  NEW_SHEET | SWITCH_SHEET | DELETE_SHEET | LIST_SHEETS |
  SET_REMINDER | DELETE_REMINDER |
  POMODORO_START | POMODORO_STOP | POMODORO_PAUSE | NOTE_CREATE |
  MORNING_BRIEFING | SYNC_NOW | WEB_SEARCH | CHAT | UNKNOWN

Output format (always return exactly this structure):
{{
  "intent": "<INTENT>",
  "confidence": <0.0-1.0>,
  "entities": {{
    "title": null,
    "sheet": null,
    "due_date": null,
    "time": null,
    "priority": null,
    "remarks": null,
    "participants": null,
    "duration_min": null,
    "status": null,
    "columns": null
  }},
  "missing_fields": [],
  "clarification_needed": null,
  "suggested_followups": []
}}

## CRITICAL CLASSIFICATION RULES

### WEB_SEARCH — use when user wants to look something up, find info, or search the internet:
- "Find me 5 best places in India" → WEB_SEARCH, remarks="5 best places in India"
- "Search for latest AI news" → WEB_SEARCH, remarks="latest AI news"
- "What is the capital of France" → WEB_SEARCH, remarks="capital of France"
- "Top restaurants in Bangalore" → WEB_SEARCH, remarks="top restaurants in Bangalore"
- "Best laptops under 50000" → WEB_SEARCH, remarks="best laptops under 50000"
- "Who won IPL 2024" → WEB_SEARCH, remarks="IPL 2024 winner"
Keywords that always mean WEB_SEARCH: find me, search for, look up, what is, who is, how to, latest, best X, top X, list of X

### CHAT — ONLY for greetings, pleasantries, thank you, help questions:
- "hi", "hello", "hey" → CHAT
- "thanks", "thank you" → CHAT
- "how are you" → CHAT
- "what can you do" → CHAT
NEVER classify "find me", "search", "what is", "who is", "how to" as CHAT.

### CONFIRMATION RESOLUTION — when user says "yes", "sure", "go ahead", "ok", "do it":
- Look at the LAST assistant message in conversation history
- Determine what action was being offered (e.g. "Would you like me to create a travel sheet?")
- Return THAT action as the intent with entities filled from context
- Example: last assistant asked "Would you like me to save these to a travel sheet?" + user says "yes" → NEW_SHEET, sheet="Travel"

### CONTEXT RESOLUTION — when user says "what are those?", "show me", "tell me more", "list them":
- If the previous search results are in history, answer from context using CHAT intent
- Do NOT re-search for the same query
- Set remarks to a summary of what the user is referring to

### OTHER RULES
- Interpret timer and Pomodoro requests as POMODORO_START/STOP/PAUSE
- Interpret note-taking as NOTE_CREATE
- If a required field is missing, add to missing_fields and set ONE clarification_needed question
- Suggest 1-2 smart follow-ups where relevant
- Never guess a sheet name — if ambiguous, ask
- Today's date: {today}
- Available sheets: {sheets}
"""

RESPONSE_SYSTEM_PROMPT = """You are VoiceDesk, a friendly voice assistant.
Generate a very brief, natural spoken response using the search results.
Limit your response to 1-2 short sentences max. Do NOT repeat or list all results in detail; just highlight the most direct answer or top 1-2 items and mention that the full list is shown on screen.
Do NOT use markdown. Speak as if talking out loud. Be extremely concise, warm, and direct.
If a follow-up question was suggested, end with it naturally.
"""


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
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Parse user transcript into structured intent JSON."""
        system = INTENT_SYSTEM_PROMPT.format(
            today=date.today().isoformat(),
            sheets=", ".join(available_sheets) if available_sheets else "none yet",
        )
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-8:])
        messages.append({"role": "user", "content": transcript})
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "messages": messages,
                    "options": {"temperature": 0.1, "num_predict": 300},
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
            logger.error(f"LLM error: {repr(e)}")
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
                    "options": {"temperature": 0.5, "num_predict": 60},
                },
            )
            text = response.json()["message"]["content"].strip()
            logger.info(f"LLM response: '{text[:80]}...'")
            return text
        except Exception as e:
            logger.error(f"LLM response error: {repr(e)}")
            return action_summary   # fallback to raw summary

    async def generate_chat_response(
        self,
        transcript: str,
        history: list[dict[str, str]] | None = None,
        context: str | None = None,
    ) -> str:
        """Generate a response for casual chat or general assistant questions."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are VoiceDesk, a friendly, helpful AI voice productivity assistant. "
                    "Act as a natural conversational partner. Keep your answers brief (1-3 sentences max), "
                    "conversational, and friendly. Do not use markdown."
                )
            }
        ]
        if context:
            messages.append({
                "role": "system",
                "content": f"Use the following search results/context to answer the user's question: {context}"
            })
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": transcript})
        
        try:
            response = await self._client.post(
                "/api/chat",
                json={
                    "model": settings.ollama_model,
                    "stream": False,
                    "messages": messages,
                    "options": {"temperature": 0.7, "num_predict": 60},
                },
            )
            text = response.json()["message"]["content"].strip()
            logger.info(f"LLM chat response: '{text[:80]}...'")
            return text
        except Exception as e:
            logger.error(f"Chat generation error: {repr(e)}")
            return "Hello! How can I help you manage your tasks, meetings, or sheets today?"


# Singleton
llm_service = LLMService()
