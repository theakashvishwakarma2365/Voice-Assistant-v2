"""
Text-to-Speech service using Piper TTS (subprocess).
Returns path to generated WAV file.
"""
import asyncio
import hashlib
import subprocess
from pathlib import Path
from app.core.config import settings
from app.core.logger import logger


class TTSService:
    def __init__(self):
        self.cache_dir = Path(settings.audio_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, text: str) -> Path:
        """Deterministic filename based on text hash."""
        h = hashlib.md5(text.encode()).hexdigest()[:12]
        return self.cache_dir / f"tts_{h}.wav"

    async def synthesise(self, text: str) -> str | None:
        """
        Convert text to WAV using Piper. Returns relative filename or None.
        Uses a file cache — repeated phrases reuse existing audio.
        """
        path = self._cache_path(text)
        if path.exists():
            logger.debug(f"TTS cache hit: {path.name}")
            return path.name

        try:
            proc = await asyncio.create_subprocess_exec(
                settings.piper_executable,
                "--model", settings.piper_voice_model,
                "--output_file", str(path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                proc.communicate(input=text.encode()), timeout=15.0
            )
            if proc.returncode == 0:
                logger.info(f"TTS generated: {path.name}")
                return path.name
            else:
                logger.error(f"Piper error: {stderr.decode()[:200]}")
                return None
        except asyncio.TimeoutError:
            logger.error("Piper TTS timeout")
            return None
        except FileNotFoundError:
            logger.error(f"Piper not found at {settings.piper_executable}")
            return None
        except Exception as e:
            logger.error(f"TTS error: {e}")
            return None

    async def cleanup_cache(self):
        """Delete old cache files if total size exceeds limit."""
        max_bytes = settings.audio_cache_max_mb * 1024 * 1024
        files = sorted(self.cache_dir.glob("tts_*.wav"), key=lambda f: f.stat().st_mtime)
        total = sum(f.stat().st_size for f in files)
        while total > max_bytes and files:
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            oldest.unlink()
            logger.debug(f"TTS cache evicted: {oldest.name}")


# Singleton
tts_service = TTSService()
