"""
VoiceDesk Server — Entry Point
FastAPI app with WebSocket audio endpoint + REST API.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.logger import logger
from app.core.scheduler import start_scheduler
from app.models.database import engine, SessionLocal, ensure_schema
from app.models.models import Base, Sheet
from app.api.routes import router
from app.api.ws_handler import handle_audio_ws
from app.services.stt_service import stt_service
from app.services.sheets_service import sheets_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("═══════════════════════════════════")
    logger.info("  VoiceDesk Server starting up...  ")
    logger.info("═══════════════════════════════════")

    # 1. Create DB tables
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    logger.info("Database tables ready ✓")

    # 2. Seed default sheets
    db = SessionLocal()
    try:
        for name in settings.default_sheet_list:
            if not db.query(Sheet).filter(Sheet.name == name).first():
                db.add(Sheet(name=name, tab_name=name))
        db.commit()
        logger.info(f"Default sheets ready: {settings.default_sheet_list}")
    finally:
        db.close()

    # 3. Load Whisper model
    stt_service.load()

    # 4. Connect Google Sheets
    if sheets_service.connect():
        logger.info("Google Sheets connected ✓")
    else:
        logger.warning("Google Sheets not connected — running without sync")

    # 5. Start background scheduler
    start_scheduler()

    logger.info(f"Server ready at http://{settings.host}:{settings.port}")
    logger.info("WebSocket endpoint: ws://voicedesk.local:8000/ws/audio")

    yield  # ← server runs here

    logger.info("VoiceDesk Server shutting down...")


app = FastAPI(
    title="VoiceDesk Server",
    description="Local AI voice productivity assistant backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from pathlib import Path

# REST routes
app.include_router(router, prefix="/api")

# Static frontend
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=FileResponse)
async def home():
    return FileResponse(static_dir / "index.html")

# WebSocket
@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    await handle_audio_ws(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        reload_dirs=["app"] if settings.debug else None,
        log_level=settings.log_level,
    )
