from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ws_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:5174", "http://localhost:3000", "http://127.0.0.1:5173"]

    # LLM provider settings
    llm_provider: str = "claude"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    groq_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4.1-mini"
    gemini_model: str = "gemini-2.5-flash"
    groq_model: str = "llama-3.3-70b-versatile"
    llm_temperature: float = 0.2
    llm_max_retries: int = 3
    llm_max_output_tokens: int = 8192

    # Agent settings
    domain_configs_dir: str = "backend/domain/configs"
    default_domain: str = "general_medicine"
    max_conversation_turns: int = 30
    intent_classifier_max_tokens: int = 10
    fact_extractor_max_tokens: int = 512
    response_generator_max_tokens: int = 200
    summarizer_max_tokens: int = 1024
    explainer_max_tokens: int = 256

    # Speech-to-text (Faster Whisper)
    whisper_model: str = "medium"
    whisper_language: str = "en"


settings = Settings()
