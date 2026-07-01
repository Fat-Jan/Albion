import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from bot import config
from bot.main import start_health_server_if_configured
from bot.store.db import init_db


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class WebAssetsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_dashboard_assets_are_present_and_wired(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        css = (WEB / "styles.css").read_text(encoding="utf-8")
        js = (WEB / "app.js").read_text(encoding="utf-8")

        self.assertIn('href="/styles.css"', html)
        self.assertIn('rel="icon" href="data:,"', html)
        self.assertIn('src="/app.js"', html)
        self.assertIn('id="invite-actions"', html)
        self.assertIn('id="dashboard-notice"', html)
        self.assertIn('id="dashboard-shell"', html)
        self.assertIn('id="status-health"', html)
        self.assertIn('id="status-health-note"', html)
        self.assertIn('aria-label="Refresh dashboard"', html)
        self.assertIn('class="ops-summary"', html)
        self.assertIn('id="summary-collectors"', html)
        self.assertIn('id="summary-signals"', html)
        self.assertIn('id="summary-guilds"', html)
        self.assertIn('class="brand-mark"', html)
        self.assertIn('class="brand-copy"', html)
        self.assertIn("/api/status", js)
        self.assertIn("/api/invites", js)
        self.assertIn("/api/events/high-fame?limit=20", js)
        self.assertIn("/api/leaderboards?limit=20", js)
        self.assertIn("/api/market/gold?limit=8", js)
        self.assertIn("/api/attendance/recent?limit=20&min_guild_players=20", js)
        self.assertIn("collector_summary", js)
        self.assertIn("renderOpsSummary", js)
        self.assertIn("renderHealth", js)
        self.assertIn("summarizeCollectors", js)
        self.assertIn("healthLabel", js)
        self.assertIn("shortList", js)
        self.assertIn("renderNotice", js)
        self.assertIn("setLoading", js)
        self.assertIn('setAttribute("aria-busy"', js)
        self.assertIn('setAttribute("aria-label"', js)
        self.assertIn("statusClass", js)
        self.assertIn("collector-row", js)
        self.assertIn("aria-disabled", js)
        self.assertIn("is-disabled", js)
        self.assertIn("participated_battles", js)
        self.assertNotIn("participated_count", js)
        self.assertIn("snapshot.battles", js)
        self.assertIn("Recent battles", js)
        self.assertIn("battleLine", js)
        self.assertIn(".status-band", css)
        self.assertIn(".ops-summary", css)
        self.assertIn(".brand-mark", css)
        self.assertIn(".panel::before", css)
        self.assertIn("tbody tr.collector-row.is-warn", css)
        self.assertIn("--mono", css)
        self.assertIn("flex: 0 0 auto", css)
        self.assertIn("grid-template-columns: repeat(5", css)
        self.assertIn(".status-note", css)
        self.assertIn(".stack > .empty", css)
        self.assertIn(".refresh-icon", css)
        self.assertIn("flex: 0 0 17px", css)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(".notice", css)
        self.assertIn(".is-loading", css)
        self.assertIn(".ops-summary > div:nth-child(3)", css)
        self.assertIn("grid-column: 1 / -1", css)

    def test_dashboard_assets_do_not_embed_secret_names_or_values(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (WEB / "index.html", WEB / "styles.css", WEB / "app.js")
        )

        for banned in (
            "KOOK_TOKEN",
            "AI_API_KEY",
            "secret-token",
            "secret-ai-key",
            "token=",
        ):
            self.assertNotIn(banned, combined)

    def test_status_server_serves_static_dashboard(self):
        port = _free_port()
        with patch.dict("os.environ", {"HEALTH_PORT": str(port), "PORT": ""}, clear=False):
            server = start_health_server_if_configured()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        with urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            html = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.headers["Content-Type"])
            self.assertIn("Ops Dashboard", html)

        with urlopen(f"http://127.0.0.1:{port}/app.js", timeout=2) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("application/javascript", response.headers["Content-Type"])
            self.assertIn("/api/status", body)


if __name__ == "__main__":
    unittest.main()
