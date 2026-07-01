"""配置加载：从环境变量 / .env 读取，不入库不进 git。"""
import base64
from dataclasses import dataclass
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


@dataclass(frozen=True)
class AlbionRegionConfig:
    region_code: str
    kook_token: str
    gameinfo_base: str
    aodp_base: str
    albionbb_base: str
    albionbb_web_base: str
    killboard_server: str
    display_tz: str
    display_tz_label: str
    display_tz_short_label: str


REGION_CODES = ("eu", "asia")
_REGION_DEFAULTS = {
    "eu": {
        "GAMEINFO_BASE": "https://gameinfo-ams.albiononline.com/api/gameinfo",
        "AODP_BASE": "https://europe.albion-online-data.com",
        "ALBIONBB_BASE": "https://api.albionbb.com/eu",
        "ALBIONBB_WEB_BASE": "https://europe.albionbb.com",
        "KILLBOARD_SERVER": "live_ams",
    },
    "asia": {
        "GAMEINFO_BASE": "https://gameinfo-sgp.albiononline.com/api/gameinfo",
        "AODP_BASE": "https://east.albion-online-data.com",
        "ALBIONBB_BASE": "https://api.albionbb.com/asia",
        "ALBIONBB_WEB_BASE": "https://east.albionbb.com",
        "KILLBOARD_SERVER": "live_sgp",
    },
}


def _normalize_region(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if text in {"eu", "europe", "ams", "live_ams"}:
        return "eu"
    if text in {"asia", "as", "east", "sgp", "live_sgp"}:
        return "asia"
    return text


def _region_env(key: str, region: str, default: str, *, url: bool = False) -> str:
    region_key = f"{key}_{region.upper()}"
    val = os.getenv(region_key, "").strip()
    if not val and region == "eu":
        val = os.getenv(key, "").strip()
    if not val:
        val = default
    return val.rstrip("/") if url else val


def _build_region_config(region: str) -> AlbionRegionConfig:
    defaults = _REGION_DEFAULTS[region]
    return AlbionRegionConfig(
        region_code=region,
        kook_token=_region_env("KOOK_TOKEN", region, ""),
        gameinfo_base=_region_env("GAMEINFO_BASE", region, defaults["GAMEINFO_BASE"], url=True),
        aodp_base=_region_env("AODP_BASE", region, defaults["AODP_BASE"], url=True),
        albionbb_base=_region_env("ALBIONBB_BASE", region, defaults["ALBIONBB_BASE"], url=True),
        albionbb_web_base=_region_env(
            "ALBIONBB_WEB_BASE", region, defaults["ALBIONBB_WEB_BASE"], url=True
        ),
        killboard_server=_region_env(
            "KILLBOARD_SERVER", region, defaults["KILLBOARD_SERVER"]
        ),
        display_tz=_region_env("DISPLAY_TZ", region, "Asia/Shanghai"),
        display_tz_label=_region_env("DISPLAY_TZ_LABEL", region, "北京时间"),
        display_tz_short_label=_region_env("DISPLAY_TZ_SHORT_LABEL", region, "北京"),
    )


REGION_CONFIGS: dict[str, AlbionRegionConfig] = {
    region: _build_region_config(region) for region in REGION_CODES
}
KOOK_REGION_CODE_LEGACY = _normalize_region(os.getenv("KOOK_REGION_CODE", "").strip())


def _default_region_code() -> str:
    if KOOK_REGION_CODE_LEGACY in REGION_CONFIGS:
        return KOOK_REGION_CODE_LEGACY
    for region, cfg in REGION_CONFIGS.items():
        if cfg.kook_token:
            return region
    return "eu"


DEFAULT_REGION_CODE = _default_region_code()
_DEFAULT_REGION_CONFIG = REGION_CONFIGS[DEFAULT_REGION_CODE]

# Backward-compatible single-region aliases. Phase 3.2 will pass region configs explicitly.
KOOK_REGION_CODE = DEFAULT_REGION_CODE
KOOK_TOKEN = _DEFAULT_REGION_CONFIG.kook_token
GAMEINFO_BASE = _DEFAULT_REGION_CONFIG.gameinfo_base
AODP_BASE = _DEFAULT_REGION_CONFIG.aodp_base
ALBIONBB_BASE = _DEFAULT_REGION_CONFIG.albionbb_base
ALBIONBB_WEB_BASE = _DEFAULT_REGION_CONFIG.albionbb_web_base
KILLBOARD_SERVER = _DEFAULT_REGION_CONFIG.killboard_server
DISPLAY_TZ = _DEFAULT_REGION_CONFIG.display_tz
DISPLAY_TZ_LABEL = _DEFAULT_REGION_CONFIG.display_tz_label
DISPLAY_TZ_SHORT_LABEL = _DEFAULT_REGION_CONFIG.display_tz_short_label
BATTLE_REPORT_WINDOW_START = os.getenv("BATTLE_REPORT_WINDOW_START", "14:30").strip() or "14:30"
BATTLE_REPORT_WINDOW_END = os.getenv("BATTLE_REPORT_WINDOW_END", "05:00").strip() or "05:00"
KOOK_BOT_MENTION_ALIASES = tuple(
    item.strip().lstrip("@")
    for item in os.getenv("KOOK_BOT_MENTION_ALIASES", "").split(",")
    if item.strip().lstrip("@")
)
WEB_PUBLIC_BASE_URL = os.getenv("WEB_PUBLIC_BASE_URL", "").strip()
KOOK_INVITE_URL_EU = os.getenv("KOOK_INVITE_URL_EU", "").strip()
KOOK_INVITE_URL_ASIA = os.getenv("KOOK_INVITE_URL_ASIA", "").strip()

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
