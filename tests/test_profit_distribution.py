"""
Regression tests for §11.1 profit allocation (no database required).
Run: python -m unittest tests.test_profit_distribution -v
"""
from __future__ import annotations

import unittest
from decimal import Decimal


class _M:
    """Dummy member stand-in."""

    def __init__(self, name: str):
        self.name = name


class TestAllocateProfitShares(unittest.TestCase):
    def test_doc_example_eleven_two(self):
        """Business doc §11.2: total paid $100k; A $10k (10%), B $5k (5%); profit $20k → A $2k, B $1k."""
        from istithmar.services.profit_distribution import allocate_profit_shares

        a, b, c = _M("A"), _M("B"), _M("C")
        pairs = [
            (a, Decimal("10000")),
            (b, Decimal("5000")),
            (c, Decimal("85000")),
        ]
        total = Decimal("100000")
        rows = allocate_profit_shares(pairs, Decimal("20000"), total)
        self.assertEqual(len(rows), 3)
        by = {r["member"].name: r["share"] for r in rows}
        self.assertEqual(by["A"], Decimal("2000.00"))
        self.assertEqual(by["B"], Decimal("1000.00"))
        self.assertEqual(by["C"], Decimal("17000.00"))
        self.assertEqual(sum(r["share"] for r in rows), Decimal("20000"))

    def test_equal_three_way_remainder_goes_to_last(self):
        from istithmar.services.profit_distribution import allocate_profit_shares

        m1, m2, m3 = _M("1"), _M("2"), _M("3")
        pairs = [(m1, Decimal("100")), (m2, Decimal("100")), (m3, Decimal("100"))]
        total = Decimal("300")
        rows = allocate_profit_shares(pairs, Decimal("100"), total)
        s = sum(r["share"] for r in rows)
        self.assertEqual(s, Decimal("100"))
        self.assertEqual(rows[0]["share"], rows[1]["share"])
        # Last row absorbs cent remainder when thirds don't divide evenly (33.33 + 33.33 + 33.34)
        self.assertEqual(rows[0]["share"], Decimal("33.33"))
        self.assertEqual(rows[2]["share"], Decimal("33.34"))

    def test_single_member_gets_full_pool(self):
        from istithmar.services.profit_distribution import allocate_profit_shares

        m = _M("solo")
        rows = allocate_profit_shares([(m, Decimal("5000"))], Decimal("123.45"), Decimal("5000"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["share"], Decimal("123.45"))


if __name__ == "__main__":
    unittest.main()
