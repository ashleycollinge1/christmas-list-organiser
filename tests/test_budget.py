from dataclasses import dataclass

from app.budget import ON, OVER, UNDER, Totals, budget_state, gift_cost, line_total


@dataclass
class G:
    price_pence: int | None
    quantity: int = 1
    my_share_pence: int | None = None
    status: str = "ordered"


def test_line_total_and_cost():
    assert line_total(G(1250, 2)) == 2500
    assert line_total(G(None)) is None
    assert gift_cost(G(10000, my_share_pence=5000)) == 5000
    assert gift_cost(G(None, my_share_pence=0)) == 0


def test_budget_state_margin():
    budget, margin = 30000, 500
    assert budget_state(29499, budget, margin) == UNDER
    assert budget_state(29500, budget, margin) == ON
    assert budget_state(30500, budget, margin) == ON
    assert budget_state(30501, budget, margin) == OVER
    assert budget_state(100, None, margin) is None


def test_totals_spent_vs_planned():
    t = Totals(budget=30000).add_gifts(
        [
            G(10000, status="idea"),
            G(5000, 2, status="ordered"),
            G(8000, my_share_pence=4000, status="wrapped"),
            G(None, status="delivered"),
        ]
    )
    d = t.to_dict(500)
    assert d["spent_pence"] == 14000
    assert d["planned_pence"] == 24000
    assert d["remaining_pence"] == 16000
    assert d["state"] == UNDER
    assert d["unpriced"] == 1
    assert d["counts"]["idea"] == 1 and d["counts"]["delivered"] == 1


def test_merge_budgets():
    a = Totals(budget=1000).add_gifts([G(500)])
    b = Totals(budget=None).add_gifts([G(700)])
    total = Totals().merge(a).merge(b)
    assert total.budget == 1000
    assert total.spent == 1200
    assert total.to_dict(0)["state"] == OVER
