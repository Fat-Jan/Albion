import unittest
from unittest.mock import patch

import httpx

from scripts.audit_item_localization import (
    build_audit,
    collect_event_item_ids,
    fetch_recent_events,
    gear_category,
    runtime_missing_ids,
)


class ItemLocalizationAuditTest(unittest.TestCase):
    def test_gear_category_covers_combat_equipment_and_consumables(self):
        cases = {
            "T8_MAIN_BOW@1": "mainhand",
            "T6_2H_DUALSWORD@2": "mainhand",
            "T5_OFF_SHIELD": "offhand",
            "T7_HEAD_LEATHER_SET1": "armor",
            "T7_ARMOR_CLOTH_SET2@3": "armor",
            "T7_SHOES_PLATE_SET3": "armor",
            "T8_BAG@1": "bag",
            "T4_CAPEITEM_FW_FORTSTERLING": "cape",
            "T5_MOUNT_HORSE": "mount",
            "T7_MEAL_OMELETTE": "food",
            "T6_POTION_HEAL@1": "potion",
        }

        for item_id, expected in cases.items():
            with self.subTest(item_id=item_id):
                self.assertEqual(gear_category(item_id), expected)

        self.assertIsNone(gear_category("T4_2H_TOOL_AXE"))
        self.assertIsNone(gear_category("UNIQUE_UNLOCK_SKIN"))

    def test_collect_event_item_ids_walks_equipment_and_inventory(self):
        event = {
            "Killer": {
                "Equipment": {
                    "MainHand": {"Type": "T8_MAIN_BOW@1"},
                    "Potion": {"Type": "T6_POTION_HEAL@1"},
                }
            },
            "Victim": {
                "Equipment": {
                    "Cape": {"Type": "T4_CAPEITEM_FW_FORTSTERLING"},
                    "Mount": {"Type": "T5_MOUNT_HORSE"},
                },
                "Inventory": [
                    {"Type": "T8_BAG@1"},
                    {"Type": "T4_2H_TOOL_AXE"},
                    {"NotType": "T7_MEAL_OMELETTE"},
                ],
            },
        }

        self.assertEqual(
            collect_event_item_ids(event),
            {
                "T8_MAIN_BOW@1",
                "T6_POTION_HEAL@1",
                "T4_CAPEITEM_FW_FORTSTERLING",
                "T5_MOUNT_HORSE",
                "T8_BAG@1",
            },
        )

    def test_runtime_missing_ids_uses_localizer_result(self):
        def localize(item_id):
            return item_id if item_id == "T8_FAKE_ITEM" else "中文名"

        self.assertEqual(
            runtime_missing_ids(["T8_MAIN_BOW@1", "T8_FAKE_ITEM"], localize),
            ["T8_FAKE_ITEM"],
        )

    def test_fetch_recent_events_stops_at_api_offset_limit(self):
        request = httpx.Request("GET", "https://example.invalid/events")
        response = httpx.Response(400, request=request)
        error = httpx.HTTPStatusError("bad offset", request=request, response=response)

        with patch(
            "scripts.audit_item_localization._fetch_json",
            side_effect=[[{"EventId": str(i)} for i in range(51)], error],
        ):
            self.assertEqual(
                fetch_recent_events(40, base_url="https://example.invalid"),
                [{"EventId": str(i)} for i in range(51)],
            )

    def test_build_audit_reports_source_runtime_missing(self):
        source_raw = [
            {"UniqueName": "T8_MAIN_BOW", "LocalizedNames": {"ZH-CN": "弓箭"}},
            {"UniqueName": "T8_MAIN_FAKE", "LocalizedNames": {}},
        ]

        audit = build_audit(source_raw, {"T8_MAIN_BOW": "弓箭"}, [])

        self.assertEqual(audit["source"]["runtime_missing"], ["T8_MAIN_FAKE"])


if __name__ == "__main__":
    unittest.main()
