"""配置加载：从环境变量 / .env 读取，不入库不进 git。"""
import os
import logging

from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(f"缺少必填环境变量 {key}（见 .env.example）")
    return val


KOOK_TOKEN = os.getenv("KOOK_TOKEN", "").strip()

GAMEINFO_BASE = os.getenv(
    "GAMEINFO_BASE", "https://gameinfo-sgp.albiononline.com/api/gameinfo"
).rstrip("/")
AODP_BASE = os.getenv("AODP_BASE", "https://east.albion-online-data.com").rstrip("/")
ALBIONBB_BASE = os.getenv("ALBIONBB_BASE", "https://api.albionbb.com/asia").rstrip("/")

DB_PATH = os.getenv("DB_PATH", "data/bot.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()


def _bool_env(key: str, default: bool = False) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _float_env(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


AI_ENABLED = _bool_env("AI_ENABLED", False)
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.longcat.chat/openai").rstrip("/")
AI_API_KEY = (os.getenv("AI_API_KEY") or os.getenv("LONGCAT_API_KEY") or "").strip()
AI_MODEL = os.getenv("AI_MODEL", "LongCat-2.0-Preview").strip()
AI_TIMEOUT_SEC = _float_env("AI_TIMEOUT_SEC", 20.0)
AI_MAX_OUTPUT_TOKENS = _int_env("AI_MAX_OUTPUT_TOKENS", 800)


def require_token() -> str:
    """启动 bot 前调用，确保 Token 存在。"""
    if not KOOK_TOKEN:
        raise RuntimeError("缺少 KOOK_TOKEN（见 .env.example）")
    return KOOK_TOKEN


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
