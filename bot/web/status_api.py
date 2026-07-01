"""Read-only HTTP API for health, status, and cached dashboard data."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bot import config
from bot.store import repo
from bot.version import __version__


class StatusAPIHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html", "/styles.css", "/app.js"}:
            self._send_static(parsed.path)
            return
        if parsed.path == "/healthz":
            self._send_text("ok\n")
            return
        if parsed.path == "/api/status":
            self._send_json(status_payload())
            return
        if parsed.path == "/api/invites":
            self._send_json(invites_payload())
            return
        if parsed.path == "/api/events/high-fame":
            params = parse_qs(parsed.query)
            limit = _int_param(params, "limit", 20, minimum=1, maximum=100)
            requested_guild = (params.get("kook_guild_id") or [""])[0] or None
            requested_region = _region_param(params)
            self._send_json(
                {
                    "items": repo.list_high_fame_events(
                        limit=limit,
                        kook_guild_id=requested_guild,
                        region=requested_region,
                    )
                }
            )
            return
        if parsed.path == "/api/leaderboards":
            params = parse_qs(parsed.query)
            limit = _int_param(params, "limit", 20, minimum=1, maximum=100)
            self._send_json({"items": repo.list_leaderboard_snapshots(limit=limit)})
            return
        if parsed.path == "/api/market/gold":
            params = parse_qs(parsed.query)
            limit = _int_param(params, "limit", 20, minimum=1, maximum=100)
            self._send_json({"items": repo.list_gold_price_snapshots(limit=limit)})
            return
        if parsed.path == "/api/attendance/recent":
            params = parse_qs(parsed.query)
            self._send_json(attendance_payload(params))
            return
        self.send_response(HTTPStatus.NOT_FOUND)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_text(self, body: str) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, path: str) -> None:
        filename = "index.html" if path in {"/", "/index.html"} else path.lstrip("/")
        content_types = {
            "index.html": "text/html; charset=utf-8",
            "styles.css": "text/css; charset=utf-8",
            "app.js": "application/javascript; charset=utf-8",
        }
        if filename not in content_types:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        asset = _web_root() / filename
        if not asset.exists():
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        body = asset.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types[filename])
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def status_payload() -> dict:
    collectors = repo.recent_collector_runs(limit=20)
    last_task_run = collectors[0]["last_run_at"] if collectors else None
    regions = {}
    for region in config.REGION_CONFIGS:
        region_collectors = [c for c in collectors if c.get("region") == region]
        bindings = repo.all_guild_bindings(region=region)
        regions[region] = {
            "collector_summary": _collector_summary(region_collectors),
            "collectors": region_collectors,
            "guilds": [
                {
                    "kook_guild_id": gb.get("kook_guild_id"),
                    "albion_guild_id": gb.get("albion_guild_id"),
                    "albion_guild_name": gb.get("albion_guild_name"),
                }
                for gb in bindings
            ],
        }
    return {
        "version": __version__,
        "region": config.KOOK_REGION_CODE,
        "regions": regions,
        "last_heartbeat": _now(),
        "last_task_run": last_task_run,
        "collector_summary": _collector_summary(collectors),
        "collectors": collectors,
    }


def invites_payload() -> dict:
    return {
        "eu": config.KOOK_INVITE_URL_EU,
        "asia": config.KOOK_INVITE_URL_ASIA,
    }


def _collector_summary(collectors: list[dict]) -> dict:
    counts = {"ok": 0, "warn": 0, "bad": 0}
    last_ok_at = None
    for collector in collectors:
        state = _collector_state(collector.get("status"))
        counts[state] += 1
        if state == "ok" and last_ok_at is None:
            last_ok_at = collector.get("last_run_at")
    if counts["bad"]:
        status = "bad"
    elif counts["warn"]:
        status = "warn"
    elif collectors:
        status = "ok"
    else:
        status = "idle"
    return {
        "status": status,
        "total": len(collectors),
        "ok": counts["ok"],
        "warn": counts["warn"],
        "bad": counts["bad"],
        "last_ok_at": last_ok_at,
    }


def _collector_state(value: object) -> str:
    normalized = str(value or "").lower()
    if normalized == "ok":
        return "ok"
    if normalized in {"partial", "warn"}:
        return "warn"
    if normalized in {"error", "failed"}:
        return "bad"
    return "warn"


def attendance_payload(params: dict[str, list[str]]) -> dict:
    limit = _int_param(params, "limit", 20, minimum=1, maximum=50)
    min_guild_players = _int_param(params, "min_guild_players", 20, minimum=1, maximum=200)
    requested_guild = (params.get("kook_guild_id") or [""])[0]
    requested_region = _region_param(params)
    bindings = repo.all_guild_bindings(region=requested_region)
    if requested_guild:
        bindings = [gb for gb in bindings if gb.get("kook_guild_id") == requested_guild]
    items = []
    for gb in bindings:
        snapshot = repo.recent_attendance_snapshot(
            gb["kook_guild_id"],
            gb["region"],
            limit=limit,
            min_guild_players=min_guild_players,
        )
        items.append(
            {
                "region": gb["region"],
                "kook_guild_id": gb["kook_guild_id"],
                "albion_guild_id": gb["albion_guild_id"],
                "albion_guild_name": gb["albion_guild_name"],
                "snapshot": snapshot,
            }
        )
    return {"items": items}


def _int_param(
    params: dict[str, list[str]],
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int((params.get(name) or [default])[0])
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _region_param(params: dict[str, list[str]]) -> str | None:
    value = (params.get("region") or [""])[0].strip().lower()
    return value if value in config.REGION_CONFIGS else None


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _web_root() -> Path:
    return Path(__file__).resolve().parents[2] / "web"
