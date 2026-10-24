"""Configurações da aplicação (stub de contrato — implementado por add-pokeapi-client)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    pokeapi_base_url: str = "https://pokeapi.co/api/v2"
    cache_dir: str = ".cache"
    cache_ttl_seconds: int = 86400
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""
    log_level: str = "INFO"
    log_file: str = ""  # vazio = só stderr; ex.: logs/pokegarden.jsonl
    pokegarden_tools_profile: str = "B"  # perfil de tools: A (sem evolução) ou B (todas)

    # Orçamentos por requisição
    request_deadline_s: float = 20.0
    http_timeout_s: float = 5.0
    max_turns: int = 6
    max_tool_calls: int = 8
    max_http_requests: int = 12
    max_message_chars: int = 2000
    max_tool_output_bytes: int = 8192


settings = Settings()
