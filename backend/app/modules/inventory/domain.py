from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class StockSummary:
    on_hand: Decimal
    reserved_demand: Decimal
    allocated: Decimal
    quarantined: Decimal = ZERO

    def __post_init__(self) -> None:
        if min(self.on_hand, self.reserved_demand, self.allocated, self.quarantined) < ZERO:
            raise ValueError("Inventory quantities cannot be negative")
        if self.quarantined > self.on_hand:
            raise ValueError("Quarantined quantity cannot exceed on-hand quantity")
        if self.allocated > self.usable_on_hand:
            raise ValueError("Allocated quantity cannot exceed usable on-hand quantity")

    @property
    def usable_on_hand(self) -> Decimal:
        return self.on_hand - self.quarantined

    @property
    def free_to_promise(self) -> Decimal:
        return self.usable_on_hand - self.allocated

    @property
    def shortage(self) -> Decimal:
        return max(self.reserved_demand - self.usable_on_hand, ZERO)
