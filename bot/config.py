"""配置加载：从环境变量 / .env 读取，不入库不进 git。"""
import base64
import hashlib
import os
import logging

from dotenv import dotenv_values, find_dotenv, load_dotenv

_DOTENV_PATH = find_dotenv(usecwd=True)
_DOTENV_VALUES = dotenv_values(_DOTENV_PATH) if _DOTENV_PATH else {}
load_dotenv(_DOTENV_PATH or None)


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
ALBIONBB_WEB_BASE = os.getenv("ALBIONBB_WEB_BASE", "https://east.albionbb.com").rstrip("/")
KILLBOARD_SERVER = os.getenv("KILLBOARD_SERVER", "live_sgp").strip() or "live_sgp"

DISPLAY_TZ = os.getenv("DISPLAY_TZ", "Asia/Shanghai").strip() or "Asia/Shanghai"
DISPLAY_TZ_LABEL = os.getenv("DISPLAY_TZ_LABEL", "北京时间").strip() or "北京时间"
DISPLAY_TZ_SHORT_LABEL = os.getenv("DISPLAY_TZ_SHORT_LABEL", "北京").strip() or "北京"
BATTLE_REPORT_WINDOW_START = os.getenv("BATTLE_REPORT_WINDOW_START", "14:30").strip() or "14:30"
BATTLE_REPORT_WINDOW_END = os.getenv("BATTLE_REPORT_WINDOW_END", "05:00").strip() or "05:00"

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


def _decode_token_bot_id(token: str) -> str:
    parts = token.split("/")
    if len(parts) < 2 or not parts[1]:
        return "unknown"
    encoded = parts[1]
    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        return base64.b64decode(padded).decode("utf-8")
    except Exception:
        return "unknown"


def token_runtime_info(
    token: str | None = None, *, env_file_token: str | None = None
) -> dict[str, str]:
    """返回可安全写入日志的 KOOK token 诊断信息。"""
    actual = (token if token is not None else KOOK_TOKEN).strip()
    env_value = (
        env_file_token
        if env_file_token is not None
        else str(_DOTENV_VALUES.get("KOOK_TOKEN") or "")
    ).strip()

    if not actual:
        source = "missing"
    elif env_value and actual == env_value:
        source = "env_file"
    elif env_value:
        source = "environment_overrides_env_file"
    else:
        source = "environment"

    return {
        "bot_id": _decode_token_bot_id(actual) if actual else "missing",
        "fingerprint": hashlib.sha256(actual.encode("utf-8")).hexdigest()[:12]
        if actual
        else "missing",
        "source": source,
    }


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
