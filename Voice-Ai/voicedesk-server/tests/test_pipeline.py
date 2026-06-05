"""
Basic pipeline tests — run with: pytest tests/
Tests run without real hardware (mocked services).
"""
import pytest
import asyncio
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

    summary, follow_up = intent_executor.execute(intent_data, db)
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
    summary, _ = intent_executor.execute(intent_data, db)
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
    summary, _ = intent_executor.execute(intent_data, db)
    assert "My Project" in summary
    sheet = db.query(Sheet).filter(Sheet.name == "My Project").first()
    assert sheet is not None
    db.close()


@pytest.mark.asyncio
async def test_llm_service_unreachable():
    """LLM service returns UNKNOWN intent gracefully when Ollama is down."""
    from app.services.llm_service import LLMService
    svc = LLMService()
    # No running Ollama → should return UNKNOWN without raising
    result = await svc.parse_intent("add a task", ["Work"])
    assert result.get("intent") in ("UNKNOWN", "ADD_TASK")  # may work if Ollama running
