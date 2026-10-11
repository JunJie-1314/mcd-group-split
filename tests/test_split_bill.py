#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""麦门拼单官 · 分账算法单元测试

运行：python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from split_bill import (  # noqa: E402
    Member,
    allocate,
    cents_to_yuan,
    format_report,
    split_bill,
    yuan_to_cents,
)


class TestAllocate(unittest.TestCase):
    def test_exact_division(self):
        self.assertEqual(allocate([1, 1, 1], 300), [100, 100, 100])

    def test_remainder_goes_to_largest_fraction(self):
        # 100 / 3 = 33.33...  向下取整各得 33，余 1 分给余数最大者（并列时按原顺序）
        self.assertEqual(allocate([1, 1, 1], 100), [34, 33, 33])

    def test_weighted(self):
        # 49.70 元按 1400:1600:1900 分摊
        self.assertEqual(allocate([1400, 1600, 1900], 4970), [1420, 1623, 1927])

    def test_sum_is_exact_via_integer_math(self):
        self.assertEqual(sum(allocate([1400, 1600, 1900], 2970)), 2970)

    def test_zero_weights_fall_back_to_even(self):
        self.assertEqual(allocate([0, 0, 0], 100), [34, 33, 33])

    def test_zero_amount(self):
        self.assertEqual(allocate([500, 500], 0), [0, 0])

    def test_single_share_takes_all(self):
        self.assertEqual(allocate([7], 1234), [1234])

    def test_rejects_negative_amount(self):
        with self.assertRaises(ValueError):
            allocate([1, 1], -1)

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            allocate([], 100)


class TestMoneyConversion(unittest.TestCase):
    def test_yuan_to_cents(self):
        self.assertEqual(yuan_to_cents("14"), 1400)
        self.assertEqual(yuan_to_cents("14.5"), 1450)
        self.assertEqual(yuan_to_cents("9.90"), 990)
        self.assertEqual(yuan_to_cents(0.1), 10)

    def test_float_safety(self):
        # 经典的 0.1 + 0.2 陷阱：用 Decimal 后必须精确
        self.assertEqual(yuan_to_cents("0.1") + yuan_to_cents("0.2"), 30)

    def test_rejects_sub_cent(self):
        with self.assertRaises(ValueError):
            yuan_to_cents("0.001")

    def test_cents_to_yuan(self):
        self.assertEqual(cents_to_yuan(2970), "29.70")
        self.assertEqual(cents_to_yuan(5), "0.05")
        self.assertEqual(cents_to_yuan(0), "0.00")


class TestSplitBill(unittest.TestCase):
    """基准场景：三张 9.9 元券，原价 ¥49.00 → 实付 ¥29.70（省 ¥19.30）。"""

    MEMBERS = (Member("小美", 1400), Member("阿强", 1600), Member("老王", 1900))

    def test_proportional_matches_hand_calculation(self):
        dues = split_bill(self.MEMBERS, total_paid=2970)
        self.assertEqual(dues, [("小美", 848), ("阿强", 970), ("老王", 1152)])

    def test_even_discount(self):
        dues = split_bill(self.MEMBERS, total_paid=2970, goods_strategy="even_discount")
        self.assertEqual(dues, [("小美", 756), ("阿强", 957), ("老王", 1257)])

    def test_total_is_conserved(self):
        for strategy in ("proportional", "even_discount"):
            for fee_strategy in ("even", "initiator", "proportional"):
                dues = split_bill(
                    self.MEMBERS,
                    total_paid=2970,
                    goods_strategy=strategy,
                    delivery_strategy=fee_strategy,
                )
                self.assertEqual(sum(a for _, a in dues), 2970)

    def test_no_one_pays_more_than_they_ordered(self):
        dues = split_bill(self.MEMBERS, total_paid=2970)
        for (_, due), m in zip(dues, self.MEMBERS):
            self.assertLessEqual(due, m.subtotal)
            self.assertGreaterEqual(due, 0)

    def test_delivery_even(self):
        dues = split_bill(
            (Member("小美", 1400), Member("阿强", 1600)),
            total_paid=3000,
            delivery_fee=300,
            delivery_strategy="even",
        )
        self.assertEqual(dues, [("小美", 1410), ("阿强", 1590)])

    def test_delivery_initiator(self):
        dues = split_bill(
            (Member("小美", 1400), Member("阿强", 1600)),
            total_paid=3000,
            delivery_fee=300,
            delivery_strategy="initiator",
        )
        self.assertEqual(dues, [("小美", 1560), ("阿强", 1440)])

    def test_delivery_proportional(self):
        dues = split_bill(
            (Member("小美", 1400), Member("阿强", 1600)),
            total_paid=3000,
            delivery_fee=300,
            delivery_strategy="proportional",
        )
        self.assertEqual(dues, [("小美", 1400), ("阿强", 1600)])

    def test_member_who_ordered_nothing(self):
        dues = split_bill(
            (Member("小美", 1400), Member("蹭饭的", 0)),
            total_paid=990,
            goods_strategy="proportional",
        )
        self.assertEqual(dues, [("小美", 990), ("蹭饭的", 0)])

    def test_single_member_pays_everything(self):
        dues = split_bill((Member("独食", 2000),), total_paid=1500, delivery_fee=300)
        self.assertEqual(dues, [("独食", 1500)])

    def test_no_discount_is_identity(self):
        dues = split_bill(self.MEMBERS, total_paid=4900)
        self.assertEqual(dues, [("小美", 1400), ("阿强", 1600), ("老王", 1900)])

    def test_rejects_invalid_delivery_fee(self):
        with self.assertRaises(ValueError):
            split_bill(self.MEMBERS, total_paid=1000, delivery_fee=2000)
        with self.assertRaises(ValueError):
            split_bill(self.MEMBERS, total_paid=1000, delivery_fee=-1)

    def test_rejects_unknown_strategy(self):
        with self.assertRaises(ValueError):
            split_bill(self.MEMBERS, total_paid=1000, goods_strategy="magic")
        with self.assertRaises(ValueError):
            split_bill(self.MEMBERS, total_paid=1000, delivery_strategy="magic")

    def test_rejects_empty_members(self):
        with self.assertRaises(ValueError):
            split_bill((), total_paid=1000)


class TestConservationStress(unittest.TestCase):
    """守恒性与合理性压测：任意参数组合下加总必须恰好等于实付。"""

    def test_exhaustive_small_space(self):
        subtotal_sets = (
            (1, 1),
            (1, 2, 3),
            (7, 7, 7),
            (100, 1, 1, 1),
            (1400, 1600, 1900),
            (333, 333, 334),
            (0, 999, 1),
        )
        for subtotals in subtotal_sets:
            members = [Member(f"m{i}", s) for i, s in enumerate(subtotals)]
            original = sum(subtotals)
            for paid in range(0, original + 1, max(original // 7, 1)):
                for delivery in (0, min(50, paid)):
                    for goods_strategy in ("proportional", "even_discount"):
                        dues = split_bill(
                            members,
                            total_paid=paid,
                            delivery_fee=delivery,
                            goods_strategy=goods_strategy,
                        )
                        self.assertEqual(
                            sum(a for _, a in dues),
                            paid,
                            msg=f"不守恒: {subtotals=} {paid=} {delivery=} {goods_strategy=}",
                        )
                        self.assertTrue(all(a >= 0 for _, a in dues), msg="出现负数应付")


class TestFormatReport(unittest.TestCase):
    def test_report_contains_key_lines(self):
        report = format_report(
            (Member("小美", 1400), Member("阿强", 1600), Member("老王", 1900)),
            total_paid=2970,
        )
        self.assertIn("麦门拼单官 · 分账账单", report)
        self.assertIn("¥29.70", report)
        self.assertIn("¥49.00", report)
        self.assertIn("小美", report)
        self.assertIn("阿强", report)
        self.assertIn("与订单实付一致", report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
