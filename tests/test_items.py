import unittest

from bot.albion import items


class ItemsTest(unittest.TestCase):
    def test_localized_uses_prototype_fallback_name(self):
        self.assertEqual(items.localized("T8_HEAD_CLOTH_PROTOTYPE@2"), "禅师级布甲头部原型+2")
        self.assertEqual(items.localized("T8_ARMOR_LEATHER_PROTOTYPE"), "禅师级皮甲胸部原型")
        self.assertEqual(items.localized("T8_SHOES_PLATE_PROTOTYPE@4"), "禅师级板甲鞋子原型+4")


if __name__ == "__main__":
    unittest.main()
