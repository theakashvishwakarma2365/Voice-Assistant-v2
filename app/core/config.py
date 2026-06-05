"""
Central configuration — loaded from .env file.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import List


class Settings(BaseSettings):
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    log_level: str = "info"
    cors_origins: str = "*"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "phi3:mini"

    # Whisper
    whisper_model: str = "base.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Piper TTS
    piper_executable: str = "/usr/local/bin/piper"
    piper_voice_model: str = "/home/pi/voicedesk/voices/en_US-lessac-medium.onnx"

    # Database
    database_url: str = "sqlite:///./voicedesk.db"

    # Google Sheets
    google_credentials_file: str = "/home/pi/voicedesk/credentials.json"
    google_spreadsheet_name: str = "VoiceDesk Data"

    # Audio cache
    audio_cache_dir: str = "./audio_cache"
    audio_cache_max_mb: int = 200

    # Default sheets
    default_sheets: str = "Work,Personal,Seed Form,Inbox"

    # Intervals
    reminder_poll_interval: int = 30
    sheets_sync_interval: int = 60
    session_timeout_seconds: int = 10

    @property
    def default_sheet_list(self) -> List[str]:
        return [s.strip() for s in self.default_sheets.split(",")]

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
