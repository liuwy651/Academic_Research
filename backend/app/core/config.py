from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# .env 在项目根目录（backend/ 的上一层）
_ROOT = Path(__file__).parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    APP_NAME: str = "Agent对话系统"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://agent:agent_password@localhost:5432/agent_db"
    REDIS_URL: str = "redis://localhost:6379/0"

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # JWT
    SECRET_KEY: str = "dev-secret-key-change-in-production-must-be-32-chars!!"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # LLM
    LLM_PROVIDER: str = "dashscope"
    LLM_MODEL: str = "qwen-turbo"
    LLM_MAX_TOKENS: int = 4096
    LLM_SYSTEM_PROMPT: str = "You are a helpful AI assistant."
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Token management (S4)
    LLM_CONTEXT_WINDOW: int = 8192   # model's total context window in tokens
    LLM_HISTORY_BUDGET: int = 4000   # max tokens reserved for conversation history


settings = Settings()
