"""KOOK 权限校验 + 提及(mention)解析。

KOOK 权限位 0 = 管理员（见官方 guild-role 文档）。绑定/设置类指令要求发起人
是服务器主或持有管理员权限的身份组。
"""
import logging
import re
from typing import Optional

from khl import Guild, User

log = logging.getLogger(__name__)

# KOOK 权限位（频道管理员及以上都算管理）：
# 0=管理员 1=管理服务器 5=管理频道 10=管理角色权限
MANAGE_BITS = (0, 1, 5, 10)

_ROLE_RE = re.compile(r"\(rol\)(\d+)\(rol\)")
_CHANNEL_RE = re.compile(r"\(chn\)(\d+)\(chn\)")
_USER_RE = re.compile(r"\(met\)(\w+)\(met\)")


async def is_guild_admin(guild: Guild, user: User) -> bool:
    """发起人是否为服务器主，或持有管理（管理员/管理服务器/管理频道/管理角色）权限。

    注意：不能用 user.fetch_roles()——KOOK 消息作者 payload 不带 guild_id，
    会以空 guild_id 请求 guild-role/list 而 400。改用 guild 拉全量身份组 +
    作者自带的 roles id 求交集。
    """
    try:
        await guild.load()  # 拿 master_id
    except Exception as exc:
        log.warning("加载公会失败: %s", exc)
    if getattr(user, "id", None) and user.id == getattr(guild, "master_id", None):
        return True

    user_role_ids = set(getattr(user, "roles", []) or [])
    if not user_role_ids:
        log.info("权限不足 user=%s 无任何身份组", getattr(user, "id", "?"))
        return False
    try:
        guild_roles = await guild.fetch_roles()
    except Exception as exc:
        log.warning("拉取公会身份组失败: %s", exc)
        return False

    combined = 0
    for r in guild_roles:
        if r.id in user_role_ids:
            combined |= r.permissions
    ok = any((combined >> b) & 1 for b in MANAGE_BITS)
    if not ok:
        log.info(
            "权限不足 user=%s combined=%s 命中身份组=%s",
            getattr(user, "id", "?"),
            combined,
            [(r.name, r.permissions) for r in guild_roles if r.id in user_role_ids],
        )
    return ok


def parse_role_id(text: str) -> Optional[str]:
    m = _ROLE_RE.search(text or "")
    if m:
        return m.group(1)
    s = (text or "").strip()
    return s if s.isdigit() else None


def parse_channel_id(text: str) -> Optional[str]:
    m = _CHANNEL_RE.search(text or "")
    if m:
        return m.group(1)
    s = (text or "").strip()
    return s if s.isdigit() else None
