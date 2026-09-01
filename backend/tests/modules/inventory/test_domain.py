from decimal import Decimal
from unittest import TestCase

from app.modules.inventory.domain import StockSummary


class StockSummaryTests(TestCase):
    def test_reports_shortage_when_demand_exceeds_usable_stock(self) -> None:
        summary = StockSummary(
            on_hand=Decimal("10"),
            reserved_demand=Decimal("16"),
            allocated=Decimal("10"),
        )

        self.assertEqual(summary.free_to_promise, Decimal("0"))
        self.assertEqual(summary.shortage, Decimal("6"))

    def test_rejects_allocation_above_usable_stock(self) -> None:
        with self.assertRaisesRegex(ValueError, "Allocated quantity"):
            StockSummary(
                on_hand=Decimal("10"),
                reserved_demand=Decimal("10"),
                allocated=Decimal("9"),
                quarantined=Decimal("2"),
            )
