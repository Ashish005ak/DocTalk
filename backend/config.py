from __future__ import annotations
 
from pathlib import Path
 
from pydantic_settings import BaseSettings, SettingsConfigDict
 
 
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
 
    ws_port: int = 8000
    default_speed: float = 1.0
    transcripts_dir: str = "backend/transcripts"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "http://127.0.0.1:5173"]
 
    # LLM provider settings 
    llm_provider: str = "claude"
    anthropic_api_key: str = ""

    openai_api_key: str = ""
    google_api_key: str = ""
    groq_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-2.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.2
    llm_max_retries: int = 3
    llm_max_output_tokens: int = 8192          # max tokens for JSON analysis calls
 
    # Context engine settings
    context_analysis_interval: int = 4          # analyse every N responder turns
    context_token_threshold_full: int = 4000    # below: send entire transcript
    context_token_threshold_summary: int = 8000 # above: LLM-summarise old turns
    context_window_size: int = 10               # recent utterances kept verbatim
 
    # Suggestion engine settings
    suggestion_max_count: int = 3               # max suggestions per batch
    suggestion_combined_mode: bool = True        # single LLM call for context+suggestions
 
    # Speech-to-text (Faster Whisper)
    whisper_model: str = "medium"
    whisper_language: str = "en"
 
    @property
    def transcripts_path(self) -> Path:
        return Path(self.transcripts_dir)
 
 
settings = Settings()