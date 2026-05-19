# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # LLM配置
    llm_api_key: str
    llm_model: str = "glm-4-long"
    llm_api_url: str = "https://api.zhipuai.com/v4/chat/completions"
    # 时间窗口配置
    time_window_minutes: int = 10
    # 数据库配置
    database_url: str = "postgresql+asyncpg://user:pass@postgres:5432/alert_analysis"
    # Redis配置
    redis_url: str = "redis://redis:6379/0"
    # 服务配置
    api_prefix: str = "/api/v1"
    debug: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()