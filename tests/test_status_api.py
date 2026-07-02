import json
import os
import socket
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from bot import config
from bot.main import start_health_server_if_configured
from bot.store.db import init_db
from bot.store import repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class StatusAPITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        self.old_token = config.KOOK_TOKEN
        self.old_ai_key = config.AI_API_KEY
        self.old_invite_eu = config.KOOK_INVITE_URL_EU
        self.old_invite_asia = config.KOOK_INVITE_URL_ASIA
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        config.KOOK_TOKEN = "secret-token"
        config.AI_API_KEY = "secret-ai-key"
        config.KOOK_INVITE_URL_EU = "https://www.kookapp.cn/oauth2/authorize?client_id=eu"
        config.KOOK_INVITE_URL_ASIA = ""
        init_db()
        self.port = _free_port()
        with patch.dict("os.environ", {"HEALTH_PORT": str(self.port), "PORT": ""}, clear=False):
            self.server = start_health_server_if_configured()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        config.DB_PATH = self.old_db
        config.KOOK_TOKEN = self.old_token
        config.AI_API_KEY = self.old_ai_key
        config.KOOK_INVITE_URL_EU = self.old_invite_eu
        config.KOOK_INVITE_URL_ASIA = self.old_invite_asia
        self.tmp.cleanup()

    def test_status_returns_safe_runtime_summary(self):
        repo.mark_collector_run(
            "attendance_battles",
            "kook-guild",
            last_run_at="2026-06-24T10:00:00Z",
        )
        repo.mark_collector_run(
            "leaderboards",
            "global",
            status="error",
            error="upstream failed",
            last_run_at="2026-06-24T10:05:00Z",
        )

        payload, raw = self.get_json("/api/status")

        self.assertIn("version", payload)
        self.assertEqual(payload["region"], config.KOOK_REGION_CODE)
        self.assertEqual(payload["last_task_run"], "2026-06-24T10:05:00Z")
        self.assertEqual(
            payload["collector_summary"],
            {
                "status": "bad",
                "total": 2,
                "ok": 1,
                "warn": 0,
                "bad": 1,
                "last_ok_at": "2026-06-24T10:00:00Z",
            },
        )
        self.assertNotIn("KOOK_TOKEN", raw)
        self.assertNotIn("AI_API_KEY", raw)
        self.assertNotIn("secret-token", raw)
        self.assertNotIn("secret-ai-key", raw)

    def test_empty_api_lists_return_arrays(self):
        high_fame, _ = self.get_json("/api/events/high-fame")
        attendance, _ = self.get_json("/api/attendance/recent")
        leaderboards, _ = self.get_json("/api/leaderboards")
        gold, _ = self.get_json("/api/market/gold")

        self.assertEqual(high_fame, {"items": []})
        self.assertEqual(attendance, {"items": []})
        self.assertEqual(leaderboards, {"items": []})
        self.assertEqual(gold, {"items": []})

    def test_attendance_recent_returns_cached_snapshot(self):
        repo.bind_guild("kook-guild", "albion-guild", "Top Squad", "admin")
        repo.save_guild_member_snapshot(
            "kook-guild",
            "albion-guild",
            [{"Id": "a", "Name": "Alice"}],
            captured_at="2026-06-24T00:00:00Z",
        )
        repo.store_battle_detail(
            "kook-guild",
            "albion-guild",
            {
                "id": "battle-1",
                "startTime": "2026-06-24T10:00:00",
                "players": [{"id": "a", "name": "Alice", "guildId": "albion-guild"}],
            },
        )

        payload, _ = self.get_json("/api/attendance/recent?limit=5&min_guild_players=1")

        self.assertEqual(payload["items"][0]["albion_guild_name"], "Top Squad")
        self.assertEqual(payload["items"][0]["snapshot"]["counted_battle_count"], 1)

    def test_invites_come_from_config(self):
        payload, _ = self.get_json("/api/invites")

        self.assertEqual(payload["eu"], config.KOOK_INVITE_URL_EU)
        self.assertEqual(payload["asia"], "")

    def test_p2_cache_payloads_are_decoded_for_dashboard(self):
        repo.save_high_fame_events(
            "kook-guild",
            "albion-guild",
            [
                {
                    "EventId": "event-1",
                    "TimeStamp": "2026-06-24T10:00:00Z",
                    "TotalVictimKillFame": 2_000_000,
                    "Killer": {"Name": "Alice", "GuildId": "albion-guild"},
                    "Victim": {"Name": "Bob", "GuildId": "other"},
                }
            ],
            min_fame=1_000_000,
        )
        repo.save_leaderboard_snapshot(
            "player_pvp_week",
            [{"Name": "Alice", "Fame": 123}],
            kook_guild_id="global",
            captured_at="2026-06-24T10:00:00Z",
        )
        repo.save_gold_price_snapshot(
            [{"timestamp": "2026-06-24T10:00:00Z", "price": 12345}],
            captured_at="2026-06-24T10:01:00Z",
        )

        high_fame, _ = self.get_json("/api/events/high-fame")
        leaderboards, _ = self.get_json("/api/leaderboards")
        gold, _ = self.get_json("/api/market/gold")

        self.assertEqual(high_fame["items"][0]["event_id"], "event-1")
        self.assertEqual(high_fame["items"][0]["killer"]["name"], "Alice")
        self.assertEqual(leaderboards["items"][0]["items"][0]["Name"], "Alice")
        self.assertEqual(gold["items"][0]["items"][0]["price"], 12345)

    def test_p2_cache_endpoints_support_limit_parameter(self):
        for idx in range(3):
            repo.save_high_fame_events(
                "kook-guild",
                "albion-guild",
                [
                    {
                        "EventId": f"event-{idx}",
                        "TimeStamp": f"2026-06-24T10:0{idx}:00Z",
                        "TotalVictimKillFame": 2_000_000 + idx,
                        "Killer": {"Name": f"Killer {idx}", "GuildId": "albion-guild"},
                        "Victim": {"Name": f"Victim {idx}", "GuildId": "other"},
                    }
                ],
            )
            repo.save_leaderboard_snapshot(
                "player_pvp_week",
                [{"Name": f"Alice {idx}", "Fame": idx}],
                captured_at=f"2026-06-24T11:0{idx}:00Z",
            )
            repo.save_gold_price_snapshot(
                [{"timestamp": f"2026-06-24T12:0{idx}:00Z", "price": 12000 + idx}],
                captured_at=f"2026-06-24T12:0{idx}:00Z",
            )

        high_fame, _ = self.get_json("/api/events/high-fame?limit=1")
        leaderboards, _ = self.get_json("/api/leaderboards?limit=1")
        gold, _ = self.get_json("/api/market/gold?limit=1")

        self.assertEqual(len(high_fame["items"]), 1)
        self.assertEqual(high_fame["items"][0]["event_id"], "event-2")
        self.assertEqual(len(leaderboards["items"]), 1)
        self.assertEqual(leaderboards["items"][0]["items"][0]["Name"], "Alice 2")
        self.assertEqual(len(gold["items"]), 1)
        self.assertEqual(gold["items"][0]["items"][0]["price"], 12002)

    def test_high_fame_endpoint_can_filter_by_kook_guild_id(self):
        event = {
            "EventId": "shared-event",
            "TimeStamp": "2026-06-24T10:00:00Z",
            "TotalVictimKillFame": 2_000_000,
            "Killer": {"Name": "Alice", "GuildId": "albion-guild"},
            "Victim": {"Name": "Bob", "GuildId": "other"},
        }
        repo.save_high_fame_events("kook-guild-a", "albion-guild", [event])
        repo.save_high_fame_events("kook-guild-b", "albion-guild", [event])

        payload, _ = self.get_json("/api/events/high-fame?kook_guild_id=kook-guild-a")

        self.assertEqual(
            [(item["kook_guild_id"], item["event_id"]) for item in payload["items"]],
            [("kook-guild-a", "shared-event")],
        )

    def get_json(self, path: str):
        with urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=2) as response:
            self.assertEqual(response.status, 200)
            raw = response.read().decode("utf-8")
        return json.loads(raw), raw


if __name__ == "__main__":
    unittest.main()
