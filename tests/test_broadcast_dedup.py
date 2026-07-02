import os
import sqlite3
import tempfile
import unittest

from bot import config
from bot.store import repo
from bot.store.db import init_db


class BroadcastDedupStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_event_broadcast_seen_is_region_scoped_and_persistent(self):
        repo.mark_event_broadcast_seen("guild", "eu", "event-1")

        self.assertTrue(repo.has_seen_event_broadcast("guild", "eu", "event-1"))
        self.assertFalse(repo.has_seen_event_broadcast("guild", "asia", "event-1"))
        self.assertFalse(repo.has_seen_event_broadcast("other-guild", "eu", "event-1"))

        conn = sqlite3.connect(config.DB_PATH)
        try:
            columns = {
                row[1]: row[5]
                for row in conn.execute("PRAGMA table_info(event_broadcast_seen)")
            }
        finally:
            conn.close()

        self.assertEqual(
            columns,
            {
                "kook_guild_id": 1,
                "region": 2,
                "event_id": 3,
                "broadcasted_at": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
