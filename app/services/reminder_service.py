"""
Reminder polling service — checks DB for due reminders and pushes to connected ESP32 clients.
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.database import SessionLocal
from app.models.models import Reminder
from app.core.logger import logger

# Reference to active WebSocket connections (set by ws_handler)
_active_connections: set = set()


def register_connection(ws):
    _active_connections.add(ws)

def unregister_connection(ws):
    _active_connections.discard(ws)


async def check_and_deliver_reminders():
    """
    Called by APScheduler every REMINDER_POLL_INTERVAL seconds.
    Finds undelivered reminders whose time has passed and pushes them.
    """
    db: Session = SessionLocal()
    try:
        due = db.query(Reminder).filter(
            Reminder.delivered == False,
            Reminder.remind_at <= datetime.utcnow(),
        ).all()

        for reminder in due:
            msg = reminder.message or "You have a reminder!"
            logger.info(f"Delivering reminder #{reminder.id}: {msg}")

            payload = {
                "type": "reminder",
                "message": msg,
                "reminder_id": reminder.id,
            }

            dead = set()
            for ws in _active_connections:
                try:
                    import json
                    await ws.send_text(json.dumps(payload))
                except Exception:
                    dead.add(ws)
            _active_connections.difference_update(dead)

            reminder.delivered = True

        if due:
            db.commit()

    except Exception as e:
        logger.error(f"Reminder check error: {e}")
    finally:
        db.close()
