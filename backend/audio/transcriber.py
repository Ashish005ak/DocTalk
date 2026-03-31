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
 
 
_HALLUCINATION_PHRASES = {
    "thank you for watching",
    "thanks for watching",
    "please subscribe",
    "like and subscribe",
    "subscribe to my channel",
    "thank you for listening",
    "thanks for listening",
    "see you next time",
    "see you in the next video",
    "bye bye",
    "goodbye",
    "thank you",
    "thanks",
    "you",
}
 
_MIN_AUDIO_DURATION = 1.0
_NO_SPEECH_THRESHOLD = 0.6
 
 
def _is_hallucination(text: str) -> bool:
    return text.strip().lower().rstrip(".!?,") in _HALLUCINATION_PHRASES
 
 
def transcribe(audio_path: str) -> str:
    """Transcribe an audio file and return the full text."""
    model = _get_model()
    language = settings.whisper_language or None
    segments, info = model.transcribe(audio_path, beam_size=5, language=language)
 
    if info.duration < _MIN_AUDIO_DURATION:
        logger.info(
            "Audio too short (%.2fs) — skipping transcription", info.duration,
        )
        return ""
 
    seg_list = list(segments)
 
    if all(seg.no_speech_prob > _NO_SPEECH_THRESHOLD for seg in seg_list):
        logger.info(
            "All segments have high no-speech probability — returning empty",
        )
        return ""
 
    text = " ".join(seg.text.strip() for seg in seg_list if seg.text.strip())
 
    if _is_hallucination(text):
        logger.info(
            "Filtered hallucinated phrase: '%s'", text,
        )
        return ""
 
    logger.info(
        "Transcribed %.1fs of audio (%s) → %d chars",
        info.duration, info.language, len(text),
    )
    return text
 
 