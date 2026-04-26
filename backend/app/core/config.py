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
    LLM_TITLE_MODEL: str = "qwen-turbo"  # 标题生成用轻量模型，避免 reasoning 模型耗尽 max_tokens
    LLM_MAX_TOKENS: int = 4096
    LLM_SYSTEM_PROMPT: str = "You are a helpful AI assistant."
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Agent 模型（独立于聊天模型，可按角色单独调优）
    # AGENT_ROUTER_MODEL：PrimaryRouter 使用带思考功能的模型，适合意图理解和直接回答
    # AGENT_WORKER_MODEL：CS_Researcher / Math_Analyst 使用不带思考过程的模型，执行效率优先
    AGENT_ROUTER_MODEL: str = "deepseek-r1"
    AGENT_WORKER_MODEL: str = "qwen-plus"

    # Token management (S4)
    LLM_CONTEXT_WINDOW: int = 32000  # model's total context window in tokens
    LLM_HISTORY_BUDGET: int = 4000   # max tokens reserved for conversation history (no-file mode)
    LLM_RESPONSE_RESERVE: int = 2048 # tokens reserved for the model's response

    # File upload (S4.5)
    UPLOAD_DIR: str = "uploads"
    MAX_FILE_SIZE_MB: int = 50
    FILE_TOKEN_BUDGET: int = 20000
    
    BOCHA_API_KEY: str = "sk-6cb6d10d13804b8b8890d623316bc75e"  # 博查网络搜索的 API Key

    # MCP filesystem server 授权目录（可在 .env 中用逗号分隔覆盖）
    MCP_FILESYSTEM_PATHS: list[str] = ["/Users/liuwy"]

    # DocMind (阿里云文档解析)
    DOCMIND_ACCESS_KEY_ID: str = ""
    DOCMIND_ACCESS_KEY_SECRET: str = ""
    DOCMIND_ENDPOINT: str = "docmind-api.cn-hangzhou.aliyuncs.com"

    # Milvus
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530

    # Embedding
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIMENSIONS: int = 1024
    EMBEDDING_BATCH_SIZE: int = 10

    # Chunking
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50


settings = Settings()
