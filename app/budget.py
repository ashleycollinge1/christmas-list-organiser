"""Budget maths. All amounts are integer pence.

- A gift's *cost* is its "my share" amount when set (joint gifts), otherwise
  price x quantity. Unpriced gifts cost nothing but are counted as unpriced.
- *Spent* counts gifts from Ordered onwards; *planned* adds Ideas on top.
- The under/on/over state compares spent with the budget, where "on" means
  within +/- the configured margin.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from .models import STATUS_IDEA, STATUSES

UNDER = "under"
ON = "on"
OVER = "over"


class GiftLike(Protocol):
    price_pence: int | None
    quantity: int
    my_share_pence: int | None
    status: str


def line_total(g: GiftLike) -> int | None:
    if g.price_pence is None:
        return None
    return g.price_pence * g.quantity


def gift_cost(g: GiftLike) -> int | None:
    if g.my_share_pence is not None:
        return g.my_share_pence
    return line_total(g)


def budget_state(spent: int, budget: int | None, margin: int) -> str | None:
    if budget is None:
        return None
    if spent < budget - margin:
        return UNDER
    if spent > budget + margin:
        return OVER
    return ON


@dataclass
class Totals:
    spent: int = 0
    planned: int = 0
    budget: int | None = None
    unpriced: int = 0
    gift_count: int = 0
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(STATUSES, 0))

    def add_gifts(self, gifts: Iterable[GiftLike]) -> Totals:
        for g in gifts:
            self.gift_count += 1
            self.counts[g.status] = self.counts.get(g.status, 0) + 1
            cost = gift_cost(g)
            if cost is None:
                self.unpriced += 1
                continue
            self.planned += cost
            if g.status != STATUS_IDEA:
                self.spent += cost
        return self

    def merge(self, other: Totals) -> Totals:
        self.spent += other.spent
        self.planned += other.planned
        self.unpriced += other.unpriced
        self.gift_count += other.gift_count
        for k, v in other.counts.items():
            self.counts[k] = self.counts.get(k, 0) + v
        if other.budget is not None:
            self.budget = (self.budget or 0) + other.budget
        return self

    def to_dict(self, margin: int) -> dict:
        state = budget_state(self.spent, self.budget, margin)
        return {
            "spent_pence": self.spent,
            "planned_pence": self.planned,
            "budget_pence": self.budget,
            "remaining_pence": None if self.budget is None else self.budget - self.spent,
            "state": state,
            "planned_state": budget_state(self.planned, self.budget, margin),
            "unpriced": self.unpriced,
            "gift_count": self.gift_count,
            "counts": self.counts,
        }
