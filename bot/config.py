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
