"""应用配置。

优先读环境变量，未设置时使用默认值。敏感配置(API Key 等)不要写死，
统一放到项目根目录 .env(已 gitignore)，通过 os.environ 读取。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根 = backend/ 上一级
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    PROJECT_NAME: str = "对话式推荐智能体"
    # 后端服务
    API_V1_PREFIX: str = ""
    CORS_ORIGINS: list[str] = [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]

    # 数据库(MySQL)
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DB: str = os.getenv("MYSQL_DB", "dialog_rec")
    DATABASE_URL: str = (
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4"
    )

    # 向量库 ChromaDB
    CHROMA_PATH: str = os.getenv("CHROMA_PATH", str(PROJECT_ROOT / "data" / "chroma"))

    # 大模型(OpenAI 兼容接口, 默认 DeepSeek)
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # 向量化(bge-m3, 本地跑)
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    EMBEDDING_DEVICE: str = os.getenv("EMBEDDING_DEVICE", "cpu")

    # JWT(登录态)
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_ALGO: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72

    # Redis(会话缓存)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

    # 成本控制：评审 Agent 开关（评测批量跑时可关，省 token）
    ENABLE_REVIEW: bool = os.getenv("ENABLE_REVIEW", "1") == "1"
    # text2sql 开关（关闭则直接用内存结构化过滤，省一次 LLM 调用）
    ENABLE_TEXT2SQL: bool = os.getenv("ENABLE_TEXT2SQL", "1") == "1"


settings = Settings()
