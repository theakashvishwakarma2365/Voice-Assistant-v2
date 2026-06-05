"""
Speech-to-Text service using faster-whisper.
Loaded once at startup, reused for all requests.
"""
import io
import numpy as np
from faster_whisper import WhisperModel
from app.core.config import settings
from app.core.logger import logger


class STTService:
    def __init__(self):
        self._model: WhisperModel | None = None

    def load(self):
        logger.info(f"Loading Whisper model: {settings.whisper_model}")
        self._model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        logger.info("Whisper model loaded ✓")

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe raw PCM bytes (16-bit signed, mono) to text.
        Returns transcript string, empty string on failure.
        """
        if not self._model:
            logger.error("Whisper model not loaded")
            return ""

        try:
            # Convert raw PCM bytes → numpy float32 array
            audio_np = (
                np.frombuffer(audio_bytes, dtype=np.int16)
                .astype(np.float32) / 32768.0
            )

            segments, info = self._model.transcribe(
                audio_np,
                beam_size=5,
                language="en",
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )

            transcript = " ".join(seg.text.strip() for seg in segments).strip()
            logger.info(f"STT transcript: '{transcript}'")
            return transcript

        except Exception as e:
            logger.error(f"STT error: {e}")
            return ""


# Singleton
stt_service = STTService()
