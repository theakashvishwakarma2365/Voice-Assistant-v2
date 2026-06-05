"""
APScheduler — background jobs: reminder polling + Google Sheets auto-sync.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.config import settings
from app.core.logger import logger

scheduler = AsyncIOScheduler()


def start_scheduler():
    from app.services.reminder_service import check_and_deliver_reminders
    from app.services.sheets_service import sheets_service
    from app.models.database import SessionLocal

    # Reminder check
    scheduler.add_job(
        check_and_deliver_reminders,
        trigger="interval",
        seconds=settings.reminder_poll_interval,
        id="reminder_check",
        replace_existing=True,
    )

    # Google Sheets auto-sync
    async def _sync_job():
        sheets_service.sync_all_background()

    scheduler.add_job(
        _sync_job,
        trigger="interval",
        seconds=settings.sheets_sync_interval,
        id="sheets_sync",
        replace_existing=True,
    )

    # TTS cache cleanup (every hour)
    async def _cache_cleanup():
        from app.services.tts_service import tts_service
        await tts_service.cleanup_cache()

    scheduler.add_job(
        _cache_cleanup,
        trigger="interval",
        hours=1,
        id="cache_cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started ✓")
