"""
SQLAlchemy engine + session factory + Base.
"""
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False, "timeout": 30},  # needed for SQLite
    echo=settings.debug,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        except Exception:
            pass
        finally:
            cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def _table_columns(conn, table: str) -> list[str]:
    try:
        rows = conn.execute(text(f"PRAGMA table_info({table})"))
        return [row[1] for row in rows]
    except Exception:
        return []


def _add_if_missing(conn, table: str, column: str, definition: str, columns: list[str]):
    if column not in columns:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
        except Exception:
            pass


def ensure_schema():
    """Apply lightweight schema migrations for existing databases."""
    if engine.url.drivername != "sqlite":
        return

    with engine.begin() as conn:
        # sheets
        sheets_cols = _table_columns(conn, "sheets")
        _add_if_missing(conn, "sheets", "custom_columns", "TEXT", sheets_cols)

        # notes
        notes_cols = _table_columns(conn, "notes")
        _add_if_missing(conn, "notes", "tags", "TEXT", notes_cols)
        _add_if_missing(conn, "notes", "updated_at", "DATETIME", notes_cols)

        # pomodoro_sessions
        pomo_cols = _table_columns(conn, "pomodoro_sessions")
        _add_if_missing(conn, "pomodoro_sessions", "paused_at", "DATETIME", pomo_cols)
        _add_if_missing(conn, "pomodoro_sessions", "paused_secs", "INTEGER DEFAULT 0", pomo_cols)

        # assistant_modes table (new — create if not exists)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS assistant_modes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id VARCHAR(200) NOT NULL,
                mode VARCHAR(30) DEFAULT 'chat',
                activated_at DATETIME,
                settings_json TEXT
            )
        """))


def get_db():
    """FastAPI dependency — yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
