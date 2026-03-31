from __future__ import annotations
 
import logging
from threading import Lock
 
from faster_whisper import WhisperModel
 
from backend.config import settings
 
logger = logging.getLogger(__name__)
 
_model: WhisperModel | None = None
_lock = Lock()
 
 
def _get_model() -> WhisperModel:
    global _model
    if _model is not None:
        return _model
    with _lock:
        if _model is not None:
            return _model
        model_size = settings.whisper_model
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        logger.info(
            "Loading Faster-Whisper model '%s' on %s (%s) …",
            model_size, device, compute_type,
        )
        _model = WhisperModel(model_size, device=device, compute_type=compute_type)
        logger.info("Faster-Whisper model loaded.")
        return _model
 
 
def warmup() -> None:
    """Pre-load the Whisper model so the first transcription call is fast."""
    _get_model()
 
 
def transcribe(audio_path: str) -> str:
    """Transcribe an audio file and return the full text."""
    model = _get_model()
    segments, info = model.transcribe(audio_path, beam_size=5)
    text = " ".join(seg.text.strip() for seg in segments if seg.text.strip())
    logger.info(
        "Transcribed %.1fs of audio (%s) → %d chars",
        info.duration, info.language, len(text),
    )
    return text
 
 