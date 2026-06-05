"""
Basic pipeline tests — run with: pytest tests/
Tests run without real hardware (mocked services).
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock


def test_intent_executor_add_task():
    """Test ADD_TASK intent creates a task in DB."""
    from app.models.database import engine, SessionLocal
    from app.models.models import Base, Sheet
    from app.services import intent_executor

    # Use in-memory SQLite for tests
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    # Seed a sheet
    db.add(Sheet(id=1, name="Work", tab_name="Work"))
    db.commit()

    intent_data = {
        "intent": "ADD_TASK",
        "entities": {
            "title": "Test task",
            "sheet": "Work",
            "due_date": "2026-12-01",
            "priority": "high",
        },
        "suggested_followups": ["Set a reminder?"],
    }

    summary, follow_up, _ = asyncio.run(intent_executor.execute(intent_data, db))
    assert "Test task" in summary
    assert follow_up == "Set a reminder?"
    db.close()


def test_intent_executor_query_tasks():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet, Task
    from app.services import intent_executor
    from datetime import datetime

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    sheet = Sheet(id=1, name="Work", tab_name="Work")
    db.add(sheet)
    db.add(Task(sheet_id=1, title="Pending task", status="pending"))
    db.add(Task(sheet_id=1, title="Done task", status="done"))
    db.commit()

    intent_data = {
        "intent": "QUERY_TASKS",
        "entities": {"sheet": "Work", "status": "pending"},
        "suggested_followups": [],
    }
    summary, _, _ = asyncio.run(intent_executor.execute(intent_data, db))
    assert "Pending task" in summary
    assert "Done task" not in summary
    db.close()


def test_intent_executor_new_sheet():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet
    from app.services import intent_executor

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    intent_data = {
        "intent": "NEW_SHEET",
        "entities": {"title": "My Project"},
        "suggested_followups": [],
    }
    summary, _, _ = asyncio.run(intent_executor.execute(intent_data, db))
    assert "My Project" in summary
    sheet = db.query(Sheet).filter(Sheet.name == "My Project").first()
    assert sheet is not None
    db.close()


def test_intent_executor_new_sheet_with_columns():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet
    from app.services import intent_executor

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    intent_data = {
        "intent": "NEW_SHEET",
        "entities": {
            "title": "Project X",
            "columns": ["Name", "Due Date", "Owner"],
        },
        "suggested_followups": [],
    }
    summary, _, _ = asyncio.run(intent_executor.execute(intent_data, db))
    assert "Project X" in summary
    sheet = db.query(Sheet).filter(Sheet.name == "Project X").first()
    assert sheet is not None
    assert sheet.custom_columns == ["Name", "Due Date", "Owner"]
    db.close()


def test_intent_executor_pomodoro_start_creates_task():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet, Task, PomodoroSession
    from app.services import intent_executor

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    sheet = Sheet(id=1, name="Personal", tab_name="Personal")
    db.add(sheet)
    db.commit()

    intent_data = {
        "intent": "POMODORO_START",
        "entities": {
            "title": "personal task",
            "sheet": "Personal",
            "duration_min": 20,
        },
        "suggested_followups": ["Would you like me to log this session in your Personal sheet?"],
    }

    summary, follow_up, debug_steps = asyncio.run(intent_executor.execute(intent_data, db))
    assert "20-minute Pomodoro" in summary
    assert "personal task" in summary
    assert follow_up == "Would you like me to log this session in your Personal sheet?"
    assert debug_steps is None or isinstance(debug_steps, list)

    task = db.query(Task).filter(Task.title == "personal task").first()
    assert task is not None
    assert task.status == "in_progress"

    session = db.query(PomodoroSession).filter(PomodoroSession.task_id == task.id).first()
    assert session is not None
    assert session.duration_min == 20
    db.close()


def test_intent_executor_unknown_note_fallback():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet, Note
    from app.services import intent_executor

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    sheet = Sheet(id=1, name="Personal", tab_name="Personal")
    db.add(sheet)
    db.commit()

    intent_data = {
        "intent": "UNKNOWN",
        "entities": {"remarks": "make a note about project ideas"},
        "suggested_followups": [],
    }

    summary, follow_up, debug_steps = asyncio.run(intent_executor.execute(intent_data, db, "make a note about project ideas"))
    assert "Saved a note" in summary
    assert follow_up is None
    assert debug_steps and "Detected a note-taking command" in debug_steps[0]

    note = db.query(Note).filter(Note.content.ilike("%project ideas%")) .first()
    assert note is not None
    db.close()


def test_intent_executor_unknown_timer_fallback():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet, Task, PomodoroSession
    from app.services import intent_executor

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    sheet = Sheet(id=1, name="Personal", tab_name="Personal")
    db.add(sheet)
    db.commit()

    intent_data = {
        "intent": "UNKNOWN",
        "entities": {"title": "personal task", "duration_min": 20},
        "suggested_followups": ["Would you like me to log this session in your Personal sheet?"],
    }

    summary, follow_up, debug_steps = asyncio.run(intent_executor.execute(intent_data, db, "start a 20 min timer for my personal task"))
    assert "Started a 20-minute Pomodoro session" in summary
    assert "personal task" in summary
    assert follow_up == "Would you like me to log this session in your Personal sheet?"
    assert debug_steps and "Detected a timer command" in debug_steps[0]

    task = db.query(Task).filter(Task.title == "personal task").first()
    assert task is not None
    assert task.status == "in_progress"

    session = db.query(PomodoroSession).filter(PomodoroSession.task_id == task.id).first()
    assert session is not None
    assert session.duration_min == 20
    db.close()


def test_intent_executor_pomodoro_start_blocked_when_active():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet, PomodoroSession
    from app.services import intent_executor

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    sheet = Sheet(id=1, name="Personal", tab_name="Personal")
    db.add(sheet)
    db.commit()

    active = PomodoroSession(task_title="existing task", duration_min=25, completed=False)
    db.add(active)
    db.commit()

    intent_data = {
        "intent": "POMODORO_START",
        "entities": {"title": "personal task", "duration_min": 20},
        "suggested_followups": ["Would you like me to log this session in your Personal sheet?"],
    }

    summary, follow_up, debug_steps = asyncio.run(intent_executor.execute(intent_data, db, "start a 20 min timer for my personal task"))
    assert "already running" in summary
    assert follow_up == "Would you like me to complete the current session first?"
    assert debug_steps and "Found existing active Pomodoro session" in debug_steps[0]

    sessions = db.query(PomodoroSession).filter(PomodoroSession.task_title == "personal task").all()
    assert len(sessions) == 0
    db.close()


def test_pomodoro_route_blocks_when_active():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base, Sheet, PomodoroSession
    from app.api.routes import start_pomodoro
    from app.models.schemas import PomodoroStart
    from fastapi import HTTPException

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    sheet = Sheet(id=1, name="Personal", tab_name="Personal")
    db.add(sheet)
    db.commit()

    active = PomodoroSession(task_title="existing task", duration_min=25, completed=False)
    db.add(active)
    db.commit()

    with pytest.raises(HTTPException) as exc:
        start_pomodoro(PomodoroStart(task_title="new task", duration_min=20), db)

    assert exc.value.status_code == 400
    assert "already running" in str(exc.value.detail)
    db.close()


def test_llm_service_unreachable():
    """LLM service returns UNKNOWN intent gracefully when Ollama is down."""
    from app.services.llm_service import LLMService
    svc = LLMService()
    # No running Ollama → should return UNKNOWN without raising
    result = asyncio.run(svc.parse_intent("add a task", ["Work"]))
    assert result.get("intent") in ("UNKNOWN", "ADD_TASK")  # may work if Ollama running


def test_intent_executor_web_search():
    """Test WEB_SEARCH intent queries search_service and returns formatted results."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base
    from app.services import intent_executor
    from unittest.mock import patch, AsyncMock

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    intent_data = {
        "intent": "WEB_SEARCH",
        "entities": {"remarks": "what is the capital of France"},
        "suggested_followups": [],
    }

    mock_results = [
        {"title": "Paris - Capital of France", "body": "Paris is the capital and most populous city of France.", "href": "https://en.wikipedia.org/wiki/Paris"}
    ]

    with patch("app.services.search_service.search_service.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_results
        summary, follow_up, _ = asyncio.run(intent_executor.execute(intent_data, db))
        mock_search.assert_called_once_with("what is the capital of France", max_results=3)
        assert "Paris" in summary
        assert "capital and most populous" in summary
        assert "Source: https://en.wikipedia.org/wiki/Paris" in summary

    db.close()


def test_intent_executor_chat_fallback():
    """Test CHAT and UNKNOWN fallbacks return None, None, None to indicate chat bypass."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base
    from app.services import intent_executor

    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    # Chat intent
    intent_data_chat = {
        "intent": "CHAT",
        "entities": {},
        "suggested_followups": [],
    }
    summary, follow_up, debug_steps = asyncio.run(intent_executor.execute(intent_data_chat, db, "hello"))
    assert summary is None
    assert follow_up is None
    assert debug_steps is None

    # Unknown general intent (no fallback note or timer)
    intent_data_unknown = {
        "intent": "UNKNOWN",
        "entities": {},
        "suggested_followups": [],
    }
    summary, follow_up, debug_steps = asyncio.run(intent_executor.execute(intent_data_unknown, db, "tell me a joke"))
    assert summary is None
    assert follow_up is None
    assert debug_steps is None

    db.close()


def test_session_store_and_confirmation():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.models.models import Base
    from app.services.session_store import session_store, is_affirmative, is_negative, resolve_confirmation_action
    from unittest.mock import patch, AsyncMock

    # Test helpers
    assert is_affirmative("yes")
    assert is_affirmative("sure")
    assert is_negative("no")
    assert is_negative("cancel")

    # Test history and pending
    sess_id = "test_sess_123"
    # clear history/pending if it was set
    session_store.clear_history(sess_id) if hasattr(session_store, "clear_history") else session_store._conversation_histories.pop(sess_id, None)
    session_store.pop_pending(sess_id)

    assert session_store.get_history(sess_id) == []
    session_store.add_message(sess_id, "user", "hi")
    assert len(session_store.get_history(sess_id)) == 1
    assert session_store.get_history(sess_id)[0]["content"] == "hi"

    session_store.set_pending(sess_id, {
        "follow_up": "Would you like me to create a travel sheet?",
        "search_summary": "Top places to visit",
        "search_query": "5 places in India",
    })
    assert session_store.get_pending(sess_id)["follow_up"] == "Would you like me to create a travel sheet?"

    # Resolve confirmation - Negative
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    res = asyncio.run(resolve_confirmation_action(sess_id, "no", db, accepted=False))
    assert res["intent"] == "CHAT"
    assert "Alright" in res["response_text"]
    assert session_store.get_pending(sess_id) == {}  # popped

    # Re-set pending for Positive confirmation test
    session_store.set_pending(sess_id, {
        "follow_up": "Would you like me to create a travel sheet?",
        "search_summary": "Top places to visit",
        "search_query": "5 places in India",
    })

    # Mock LLM and intent executor for positive resolution
    with patch("app.services.llm_service.llm_service.parse_intent", new_callable=AsyncMock) as mock_parse, \
         patch("app.services.llm_service.llm_service.generate_response", new_callable=AsyncMock) as mock_gen, \
         patch("app.services.intent_executor.execute", new_callable=AsyncMock) as mock_exec:
        
        mock_parse.return_value = {
            "intent": "NEW_SHEET",
            "entities": {"title": "Travel Sheet"},
            "suggested_followups": []
        }
        mock_gen.return_value = "Created new sheet 'Travel Sheet'."
        mock_exec.return_value = ("Created new sheet 'Travel Sheet'.", None, ["debug step"])

        res_ok = asyncio.run(resolve_confirmation_action(sess_id, "yes", db, accepted=True))
        assert res_ok["intent"] == "NEW_SHEET"
        assert "Created new sheet" in res_ok["response_text"]
        assert res_ok["sheets_sync"] is True

    db.close()



