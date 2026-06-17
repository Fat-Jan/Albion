"""Create/reuse region-prefixed KOOK channel layout and optionally write SQLite.

This is an ops helper for dual-region local bots. It intentionally only reuses
channels whose names match the current region prefix; plain or other-region
channels are left untouched.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from khl import Bot

from bot import config, region_scope
from bot.commands import admin
from bot.store import db, repo


@dataclass(frozen=True)
class PlannedChannel:
    field: str
    name: str
    channel: object | None = None

    @property
    def exists(self) -> bool:
        return self.channel is not None


CHANNEL_FIELDS: dict[str, str] = {
    **admin.OPERATIONS_CENTER_CHANNELS,
    **admin.REGEAR_CENTER_CHANNELS,
}
CATEGORY_NAMES = (
    admin.OPERATIONS_CENTER_CATEGORY_NAME,
    admin.REGEAR_CENTER_CATEGORY_NAME,
)


def plan_region_layout(channels: list[object], fields: dict[str, str] | None = None) -> dict[str, PlannedChannel]:
    """Return current-region channel matches, never plain or other-region ones."""
    fields = fields or CHANNEL_FIELDS
    planned: dict[str, PlannedChannel] = {}
    for field, base_name in fields.items():
        scoped = region_scope.scoped_name(base_name)
        channel = next(
            (
                candidate
                for candidate in channels
                if getattr(candidate, "name", None) == scoped
                and region_scope.is_reusable_region_channel(candidate)
            ),
            None,
        )
        planned[field] = PlannedChannel(field=field, name=scoped, channel=channel)
    return planned


def _find_category(categories: list[object], base_name: str) -> object | None:
    scoped = region_scope.scoped_name(base_name)
    return next(
        (
            category
            for category in categories
            if getattr(category, "name", None) == scoped
            and region_scope.is_reusable_region_channel(category)
        ),
        None,
    )


async def ensure_region_layout(guild) -> tuple[dict[str, object], dict[str, object]]:
    """Ensure both category groups and text channels exist for this region."""
    categories = await guild.fetch_channel_category_list()
    operations_category = _find_category(categories, admin.OPERATIONS_CENTER_CATEGORY_NAME)
    regear_category = _find_category(categories, admin.REGEAR_CENTER_CATEGORY_NAME)
    if operations_category is None:
        operations_category = await guild.create_channel_category(
            region_scope.scoped_name(admin.OPERATIONS_CENTER_CATEGORY_NAME)
        )
    if regear_category is None:
        regear_category = await guild.create_channel_category(
            region_scope.scoped_name(admin.REGEAR_CENTER_CATEGORY_NAME)
        )

    channels_existing = await guild.fetch_channel_list()
    planned = plan_region_layout(channels_existing)
    channels: dict[str, object] = {}
    for field, item in planned.items():
        if item.channel is not None:
            channels[field] = item.channel
            continue
        category = regear_category if field in admin.REGEAR_CENTER_CHANNELS else operations_category
        channels[field] = await guild.create_text_channel(item.name, category)
    return (
        {
            "operations": operations_category,
            "regear": regear_category,
        },
        channels,
    )


def write_binding_channels(guild_id: str, channels: dict[str, object]) -> None:
    for field in CHANNEL_FIELDS:
        repo.set_setting(guild_id, field, str(channels[field].id))


async def _close_bot_session(bot: Bot) -> None:
    requester = getattr(getattr(bot, "client", None), "gate", None)
    requester = getattr(requester, "requester", None)
    session = getattr(requester, "_cs", None)
    if session is not None and not session.closed:
        await session.close()
    if requester is not None:
        requester._cs = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guild-id", required=True, help="KOOK guild/server id to normalize")
    parser.add_argument(
        "--write-db",
        action="store_true",
        help="write the created/reused region channel ids into guild_binding",
    )
    return parser


async def _amain(args: argparse.Namespace) -> None:
    db.init_db()
    if args.write_db and not repo.get_guild_binding(args.guild_id):
        raise SystemExit(f"guild_binding not found for {args.guild_id}; bind guild before --write-db")

    bot = Bot(token=config.require_token())
    try:
        guild = await bot.client.fetch_guild(args.guild_id)
        categories, channels = await ensure_region_layout(guild)
        if args.write_db:
            write_binding_channels(args.guild_id, channels)
        print(f"region={region_scope.region_code()} guild_id={args.guild_id} write_db={args.write_db}")
        for key in ("operations", "regear"):
            category = categories[key]
            print(f"category.{key} id={category.id} name={category.name}")
        for field in CHANNEL_FIELDS:
            channel = channels[field]
            print(f"{field} id={channel.id} name={channel.name}")
    finally:
        await _close_bot_session(bot)


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_amain(args))


if __name__ == "__main__":
    main()
