"""
Centralised logging using loguru.
"""
import sys
from loguru import logger
from app.core.config import settings

logger.remove()
logger.add(
    sys.stdout,
    level=settings.log_level.upper(),
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - {message}",
    colorize=True,
)
logger.add(
    "logs/voicedesk.log",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} - {message}",
)
