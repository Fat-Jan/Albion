import os
import tempfile
import unittest

from bot import config
from bot.albion import valuation
from bot.store import repo
from bot.store.db import init_db


class PriceReferenceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db = config.DB_PATH
        config.DB_PATH = os.path.join(self.tmp.name, "bot.db")
        init_db()

    def tearDown(self):
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def test_repo_upserts_price_reference(self):
        repo.upsert_price_references(
            [
                {
                    "item_id": "T8_MAIN_SPEAR_KEEPER@1",
                    "quality": 4,
                    "slot_group": "mainhand",
                    "low_price": 777,
                    "sample_count": 2,
                    "source": "test",
                }
            ]
        )

        row = repo.get_price_reference("T8_MAIN_SPEAR_KEEPER@1", 4)

        self.assertEqual(row["low_price"], 777)
        self.assertEqual(row["slot_group"], "mainhand")
        self.assertEqual(row["sample_count"], 2)
        self.assertIsNotNone(row["updated_at"])

    def test_reference_item_filter_covers_t4_to_t8_and_enchants(self):
        from bot.albion import price_reference

        self.assertTrue(price_reference.is_reference_item("T4_2H_DUALSWORD@4"))
        self.assertTrue(price_reference.is_reference_item("T8_MAIN_SPEAR_KEEPER"))
        self.assertTrue(price_reference.is_reference_item("T6_OFF_SHIELD@2"))
        self.assertFalse(price_reference.is_reference_item("T3_2H_DUALSWORD"))
        self.assertFalse(price_reference.is_reference_item("T9_MAIN_SPEAR_KEEPER"))
        self.assertFalse(price_reference.is_reference_item("T5_2H_TOOL_PICK"))
        self.assertFalse(price_reference.is_reference_item("T5_HEAD_PLATE_SET1"))

        expanded = price_reference.expand_enchants(["T4_2H_DUALSWORD", "T5_OFF_SHIELD@2"])

        self.assertEqual(
            expanded,
            [
                "T4_2H_DUALSWORD",
                "T4_2H_DUALSWORD@1",
                "T4_2H_DUALSWORD@2",
                "T4_2H_DUALSWORD@3",
                "T4_2H_DUALSWORD@4",
                "T5_OFF_SHIELD",
                "T5_OFF_SHIELD@1",
                "T5_OFF_SHIELD@2",
                "T5_OFF_SHIELD@3",
                "T5_OFF_SHIELD@4",
            ],
        )

    async def test_refresh_upserts_low_reference_prices(self):
        from bot.albion import price_reference

        stats = await price_reference.refresh_weapon_price_reference(
            FakeReferenceMarket(),
            item_ids=["T4_2H_DUALSWORD", "T5_OFF_SHIELD@2"],
            qualities=(2, 4),
            batch_size=50,
        )

        self.assertEqual(stats["items"], 10)
        self.assertEqual(stats["records"], 2)
        self.assertEqual(repo.get_price_reference("T4_2H_DUALSWORD@1", 2)["low_price"], 1000)
        self.assertEqual(repo.get_price_reference("T5_OFF_SHIELD", 4)["low_price"], 500)

    async def test_valuation_uses_cached_weapon_reference_when_live_prices_missing(self):
        repo.upsert_price_references(
            [
                {
                    "item_id": "T8_MAIN_SPEAR_KEEPER@1",
                    "quality": 4,
                    "slot_group": "mainhand",
                    "low_price": 777,
                    "sample_count": 1,
                    "source": "test",
                }
            ]
        )
        event = {
            "Victim": {
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4, "Count": 1}
                }
            }
        }

        result = await valuation.estimate(event, MissingPriceMarket())

        self.assertEqual(result["total"], 777)
        self.assertEqual(result["items"][0]["unit"], 777)

    async def test_valuation_total_excludes_inventory_items(self):
        event = {
            "Victim": {
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4, "Count": 1}
                },
                "Inventory": [
                    {"Type": "T8_BAG", "Quality": 1, "Count": 1},
                    {"Type": "T8_CAPE", "Quality": 1, "Count": 2},
                ],
            }
        }

        result = await valuation.estimate(event, FixedPriceMarket())

        self.assertEqual(result["total"], 1000)
        self.assertEqual(sum(i["value"] for i in result["items"] if i["slot"]), 1000)
        self.assertEqual(sum(i["value"] for i in result["items"] if not i["slot"]), 3000)

    async def test_valuation_summary_splits_equipment_and_inventory_value(self):
        event = {
            "Victim": {
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_SPEAR_KEEPER@1", "Quality": 4, "Count": 1}
                },
                "Inventory": [
                    {"Type": "T8_BAG", "Quality": 1, "Count": 1},
                    {"Type": "T8_CAPE", "Quality": 1, "Count": 2},
                ],
            }
        }

        result = await valuation.estimate(event, FixedPriceMarket())

        self.assertEqual(
            valuation.summary(result),
            {
                "equipment_total": 1000,
                "inventory_total": 3000,
                "loss_total": 4000,
            },
        )

    async def test_valuation_falls_back_to_other_quality_live_price(self):
        event = {
            "Victim": {
                "Equipment": {
                    "Shoes": {"Type": "T7_SHOES_PLATE_SET3@1", "Quality": 2, "Count": 1}
                }
            }
        }

        result = await valuation.estimate(event, OtherQualityMarket())

        self.assertEqual(result["total"], 8500)
        self.assertEqual(result["items"][0]["unit"], 8500)

    async def test_valuation_falls_back_to_other_quality_history_price(self):
        event = {
            "Victim": {
                "Equipment": {
                    "MainHand": {"Type": "T5_2H_DUALMACE_AVALON@2", "Quality": 2, "Count": 1}
                }
            }
        }

        result = await valuation.estimate(event, OtherQualityHistoryMarket())

        self.assertEqual(result["total"], 255000)
        self.assertEqual(result["items"][0]["unit"], 255000)

    async def test_valuation_queries_other_quality_history_when_same_quality_missing(self):
        event = {
            "Victim": {
                "Equipment": {
                    "MainHand": {"Type": "T5_2H_DUALMACE_AVALON@2", "Quality": 2, "Count": 1}
                }
            }
        }
        market = StrictOtherQualityHistoryMarket()

        result = await valuation.estimate(event, market)

        self.assertIn(3, market.history_qualities)
        self.assertEqual(result["total"], 255000)
        self.assertEqual(result["items"][0]["unit"], 255000)

    async def test_valuation_caps_extreme_live_fallback_with_weapon_reference(self):
        repo.upsert_price_references(
            [
                {
                    "item_id": "T4_2H_SHAPESHIFTER_AVALON",
                    "quality": 1,
                    "slot_group": "mainhand",
                    "low_price": 99999,
                    "sample_count": 1,
                    "source": "test",
                }
            ]
        )
        event = {
            "Victim": {
                "Equipment": {
                    "MainHand": {"Type": "T4_2H_SHAPESHIFTER_AVALON", "Quality": 1, "Count": 1}
                }
            }
        }

        result = await valuation.estimate(event, ExtremeLiveFallbackMarket())

        self.assertEqual(result["total"], 99999)
        self.assertEqual(result["items"][0]["unit"], 99999)

    async def test_valuation_total_matches_equipment_item_values_after_rounding(self):
        event = {
            "Victim": {
                "Equipment": {
                    "MainHand": {"Type": "T5_2H_DUALMACE_AVALON@2", "Quality": 2, "Count": 1},
                    "OffHand": {"Type": "T5_OFF_SHIELD@2", "Quality": 2, "Count": 1},
                }
            }
        }

        result = await valuation.estimate(event, FractionalFallbackMarket())

        self.assertEqual(result["total"], sum(i["value"] for i in result["items"] if i["slot"]))


class FakeReferenceMarket:
    async def prices(self, items, locations=None, qualities=None):
        return [
            {
                "item_id": "T4_2H_DUALSWORD@1",
                "quality": 2,
                "city": "Caerleon",
                "sell_price_min": 1000,
            },
            {
                "item_id": "T4_2H_DUALSWORD@1",
                "quality": 2,
                "city": "Thetford",
                "sell_price_min": 1200,
            },
            {
                "item_id": "T4_2H_DUALSWORD@1",
                "quality": 2,
                "city": "Bridgewatch",
                "sell_price_min": 999999,
            },
            {
                "item_id": "T5_OFF_SHIELD",
                "quality": 4,
                "city": "Caerleon",
                "sell_price_min": 500,
            },
        ]


class MissingPriceMarket:
    async def history(self, items, locations=None, qualities=None, time_scale=24):
        return []

    async def prices(self, items, locations=None, qualities=None):
        raise RuntimeError("market unavailable")


class FixedPriceMarket:
    async def history(self, items, locations=None, qualities=None, time_scale=24):
        prices = {
            "T8_MAIN_SPEAR_KEEPER@1": 1000,
            "T8_BAG": 1000,
            "T8_CAPE": 1000,
        }
        out = []
        for item in items:
            out.append(
                {
                    "item_id": item,
                    "quality": 4 if item == "T8_MAIN_SPEAR_KEEPER@1" else 1,
                    "location": "Caerleon",
                    "data": [{"avg_price": prices[item]}],
                }
            )
        return out

    async def prices(self, items, locations=None, qualities=None):
        return []


class OtherQualityMarket:
    async def history(self, items, locations=None, qualities=None, time_scale=24):
        return []

    async def prices(self, items, locations=None, qualities=None):
        if 1 not in [int(q) for q in qualities]:
            return []
        return [
            {
                "item_id": "T7_SHOES_PLATE_SET3@1",
                "quality": 1,
                "city": "Caerleon",
                "sell_price_min": 10000,
            }
        ]


class OtherQualityHistoryMarket:
    async def history(self, items, locations=None, qualities=None, time_scale=24):
        return [
            {
                "item_id": "T5_2H_DUALMACE_AVALON@2",
                "quality": 3,
                "location": "Martlock",
                "data": [{"avg_price": 300000}],
            }
        ]

    async def prices(self, items, locations=None, qualities=None):
        return []


class StrictOtherQualityHistoryMarket:
    def __init__(self):
        self.history_qualities = []

    async def history(self, items, locations=None, qualities=None, time_scale=24):
        self.history_qualities = [int(q) for q in qualities]
        if 3 not in self.history_qualities:
            return []
        return [
            {
                "item_id": "T5_2H_DUALMACE_AVALON@2",
                "quality": 3,
                "location": "Martlock",
                "data": [{"avg_price": 300000}],
            }
        ]

    async def prices(self, items, locations=None, qualities=None):
        return []


class ExtremeLiveFallbackMarket:
    async def history(self, items, locations=None, qualities=None, time_scale=24):
        return []

    async def prices(self, items, locations=None, qualities=None):
        return [
            {
                "item_id": "T4_2H_SHAPESHIFTER_AVALON",
                "quality": 1,
                "city": "Caerleon",
                "sell_price_min": 9999999,
            }
        ]


class FractionalFallbackMarket:
    async def history(self, items, locations=None, qualities=None, time_scale=24):
        return [
            {
                "item_id": item,
                "quality": 3,
                "location": "Martlock",
                "data": [{"avg_price": 100001}],
            }
            for item in items
        ]

    async def prices(self, items, locations=None, qualities=None):
        return []
