"""Unit tests for asset_service against the in-memory adapter. No database."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.asset import Asset, AssetContribution, AssetLoan, AssetLoanBalanceCorrection, AssetValuation
from app.models.expense import Expense
from app.models.recurring_expense import RecurringExpense
from app.ports.read_models import AssetExpenseLink
from app.services import asset_service
from tests.unit.conftest import make_asset, make_category, make_expense, make_user, seed

TODAY = date(2026, 6, 15)

LOAN = {
    "original_amount_cents": 32000000,
    "annual_interest_rate": Decimal("0.0625"),
    "term_months": 360,
    "first_payment_date": date(2020, 7, 1),
    "monthly_payment_cents": None,
    "escrow_monthly_cents": 40000,
}

HOUSE = {
    "name": "Maple St",
    "asset_type": "house",
    "purchase_date": date(2020, 6, 1),
    "purchase_price_cents": 40000000,
    "down_payment_cents": 8000000,
    "closing_costs_cents": 600000,
    "state": "NC",
    "zip_code": "27601",
}


async def _asset(uow, family_id, **overrides) -> Asset:
    user = make_user()
    asset = make_asset(family_id, user.id, **overrides)
    await seed(uow, user, asset)
    return asset


async def _status(coro) -> int:
    with pytest.raises(HTTPException) as exc:
        await coro
    return exc.value.status_code


# ---------------------------------------------------------------------------
# create / list / get
# ---------------------------------------------------------------------------


async def test_create_asset_persists_fields_and_nested_loan(uow, family_id) -> None:
    user = make_user()
    await seed(uow, user)

    asset = await asset_service.create_asset(uow, family_id, user.id, fields=dict(HOUSE), loan=dict(LOAN))

    assert asset.id is not None and asset.family_id == family_id and asset.created_by_user_id == user.id
    assert asset.name == "Maple St" and asset.down_payment_cents == 8000000
    loan = await uow.asset_loans.get_for_asset(asset.id)
    assert loan is not None and loan.original_amount_cents == 32000000 and loan.escrow_monthly_cents == 40000


async def test_create_asset_without_loan_has_none(uow, family_id) -> None:
    user = make_user()
    await seed(uow, user)

    asset = await asset_service.create_asset(uow, family_id, user.id, fields=dict(HOUSE), loan=None)

    assert await uow.asset_loans.get_for_asset(asset.id) is None


async def test_create_house_without_location_is_422(uow, family_id) -> None:
    user = make_user()
    await seed(uow, user)
    fields = {**HOUSE, "state": None, "zip_code": None}

    assert await _status(asset_service.create_asset(uow, family_id, user.id, fields=fields, loan=None)) == 422


async def test_list_assets_is_scoped_to_the_family(uow, family_id) -> None:
    mine = await _asset(uow, family_id, name="Mine")
    await _asset(uow, uuid.uuid4(), name="Theirs")

    assets = await asset_service.list_assets(uow, family_id)

    assert [a.id for a in assets] == [mine.id]


async def test_get_asset_in_another_family_is_404(uow, family_id) -> None:
    other = await _asset(uow, uuid.uuid4())

    assert await _status(asset_service.get_asset(uow, family_id, other.id)) == 404


async def test_load_detail_returns_children(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.upsert_loan(uow, family_id, asset.id, fields=dict(LOAN))
    await asset_service.add_correction(uow, family_id, asset.id, as_of_date=date(2023, 1, 1), balance_cents=30000000)
    await asset_service.add_valuation(
        uow, family_id, asset.id, as_of_date=date(2024, 1, 1), value_cents=45000000, note=None
    )
    await asset_service.add_contribution(
        uow,
        family_id,
        asset.id,
        fields={"contribution_date": date(2021, 1, 1), "amount_cents": 500000, "role": "improvement"},
    )

    detail = await asset_service.load_detail(uow, asset)

    assert detail.loan is not None
    assert [c.balance_cents for c in detail.corrections] == [30000000]
    assert [v.value_cents for v in detail.valuations] == [45000000]
    assert [c.amount_cents for c in detail.contributions] == [500000]


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_asset_changes_only_given_fields_and_can_clear(uow, family_id) -> None:
    asset = await _asset(uow, family_id, address_line1="1 Main St", city="Raleigh")

    updated = await asset_service.update_asset(
        uow, family_id, asset.id, fields={"name": "Renamed", "address_line1": None}
    )

    assert updated.name == "Renamed" and updated.address_line1 is None
    assert updated.city == "Raleigh" and updated.purchase_price_cents == 40000000


async def test_update_to_house_without_location_is_422(uow, family_id) -> None:
    asset = await _asset(uow, family_id, asset_type="other")

    status = await _status(asset_service.update_asset(uow, family_id, asset.id, fields={"asset_type": "house"}))

    assert status == 422


async def test_update_clearing_house_location_is_422(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    assert await _status(asset_service.update_asset(uow, family_id, asset.id, fields={"zip_code": None})) == 422


async def test_update_purchase_date_after_sale_is_422(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.sell_asset(
        uow, family_id, asset.id, sold_date=date(2024, 1, 1), sale_price_cents=1, selling_costs_cents=0, today=TODAY
    )

    status = await _status(
        asset_service.update_asset(uow, family_id, asset.id, fields={"purchase_date": date(2025, 1, 1)})
    )

    assert status == 422


async def test_update_unknown_asset_is_404(uow, family_id) -> None:
    assert await _status(asset_service.update_asset(uow, family_id, uuid.uuid4(), fields={"name": "x"})) == 404


# ---------------------------------------------------------------------------
# sell / un-sell
# ---------------------------------------------------------------------------


async def test_sell_asset_sets_sale_fields(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    sold = await asset_service.sell_asset(
        uow,
        family_id,
        asset.id,
        sold_date=date(2025, 3, 1),
        sale_price_cents=50000000,
        selling_costs_cents=300000,
        today=TODAY,
    )

    assert sold.is_sold
    assert (sold.sold_date, sold.sale_price_cents, sold.selling_costs_cents) == (date(2025, 3, 1), 50000000, 300000)


async def test_sell_twice_is_409(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.sell_asset(
        uow, family_id, asset.id, sold_date=date(2025, 3, 1), sale_price_cents=1, selling_costs_cents=0, today=TODAY
    )

    status = await _status(
        asset_service.sell_asset(
            uow, family_id, asset.id, sold_date=date(2025, 4, 1), sale_price_cents=2, selling_costs_cents=0, today=TODAY
        )
    )

    assert status == 409


async def test_sell_before_purchase_is_422(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    status = await _status(
        asset_service.sell_asset(
            uow, family_id, asset.id, sold_date=date(2019, 1, 1), sale_price_cents=1, selling_costs_cents=0, today=TODAY
        )
    )

    assert status == 422


async def test_sell_on_a_future_date_is_422(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    status = await _status(
        asset_service.sell_asset(
            uow,
            family_id,
            asset.id,
            sold_date=date(2026, 6, 16),
            sale_price_cents=1,
            selling_costs_cents=0,
            today=TODAY,
        )
    )

    assert status == 422


async def test_sell_today_is_allowed(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    sold = await asset_service.sell_asset(
        uow, family_id, asset.id, sold_date=TODAY, sale_price_cents=1, selling_costs_cents=0, today=TODAY
    )

    assert sold.sold_date == TODAY


async def test_unsell_clears_sale_fields(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.sell_asset(
        uow,
        family_id,
        asset.id,
        sold_date=date(2025, 3, 1),
        sale_price_cents=50000000,
        selling_costs_cents=300000,
        today=TODAY,
    )

    unsold = await asset_service.unsell_asset(uow, family_id, asset.id)

    assert not unsold.is_sold
    assert (unsold.sold_date, unsold.sale_price_cents, unsold.selling_costs_cents) == (None, None, None)


async def test_unsell_an_unsold_asset_is_409(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    assert await _status(asset_service.unsell_asset(uow, family_id, asset.id)) == 409


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_asset_unlinks_expenses_and_recurring(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    category = make_category(family_id, "Home")
    user = make_user()
    linked = make_expense(family_id, category.id, user_id=user.id)
    linked.asset_id, linked.asset_role = asset.id, "maintenance"
    other_asset = await _asset(uow, family_id, name="Other")
    kept = make_expense(family_id, category.id, user_id=user.id)
    kept.asset_id, kept.asset_role = other_asset.id, "improvement"
    rule = RecurringExpense(
        family_id=family_id,
        user_id=user.id,
        category_id=category.id,
        amount_cents=100,
        frequency="monthly",
        start_date=date(2026, 1, 1),
        next_due_date=date(2026, 2, 1),
        asset_id=asset.id,
        asset_role="loan_payment",
    )
    await seed(uow, category, user, linked, kept, rule)

    await asset_service.delete_asset(uow, family_id, asset.id)

    assert uow.store.get(Asset, asset.id) is None
    assert (linked.asset_id, linked.asset_role) == (None, None)
    assert (rule.asset_id, rule.asset_role) == (None, None)
    assert (kept.asset_id, kept.asset_role) == (other_asset.id, "improvement")
    assert uow.store.get(Expense, linked.id) is linked  # the expense itself survives


async def test_delete_unknown_asset_is_404(uow, family_id) -> None:
    assert await _status(asset_service.delete_asset(uow, family_id, uuid.uuid4())) == 404


# ---------------------------------------------------------------------------
# loan + corrections
# ---------------------------------------------------------------------------


async def test_upsert_loan_creates_then_updates_in_place(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    created = await asset_service.upsert_loan(uow, family_id, asset.id, fields=dict(LOAN))
    updated = await asset_service.upsert_loan(
        uow, family_id, asset.id, fields={**LOAN, "annual_interest_rate": Decimal("0.05")}
    )

    assert updated.id == created.id and updated.annual_interest_rate == Decimal("0.05")
    assert len(uow.store.rows(AssetLoan)) == 1


async def test_delete_loan_removes_it(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.upsert_loan(uow, family_id, asset.id, fields=dict(LOAN))

    await asset_service.delete_loan(uow, family_id, asset.id)

    assert await uow.asset_loans.get_for_asset(asset.id) is None


async def test_delete_missing_loan_is_404(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    assert await _status(asset_service.delete_loan(uow, family_id, asset.id)) == 404


async def test_add_correction_requires_a_loan(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    status = await _status(
        asset_service.add_correction(uow, family_id, asset.id, as_of_date=date(2023, 1, 1), balance_cents=1)
    )

    assert status == 404


async def test_duplicate_correction_date_is_409_and_keeps_the_request_alive(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.upsert_loan(uow, family_id, asset.id, fields=dict(LOAN))
    await asset_service.add_correction(uow, family_id, asset.id, as_of_date=date(2023, 1, 1), balance_cents=1)

    status = await _status(
        asset_service.add_correction(uow, family_id, asset.id, as_of_date=date(2023, 1, 1), balance_cents=2)
    )

    assert status == 409
    assert len(uow.store.rows(AssetLoanBalanceCorrection)) == 1


async def test_delete_correction(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.upsert_loan(uow, family_id, asset.id, fields=dict(LOAN))
    correction = await asset_service.add_correction(
        uow, family_id, asset.id, as_of_date=date(2023, 1, 1), balance_cents=1
    )

    await asset_service.delete_correction(uow, family_id, asset.id, correction.id)

    assert uow.store.rows(AssetLoanBalanceCorrection) == []
    assert await _status(asset_service.delete_correction(uow, family_id, asset.id, correction.id)) == 404


# ---------------------------------------------------------------------------
# valuations
# ---------------------------------------------------------------------------


async def test_add_and_delete_valuation(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    valuation = await asset_service.add_valuation(
        uow, family_id, asset.id, as_of_date=date(2024, 1, 1), value_cents=45000000, note="Zillow"
    )
    assert valuation.note == "Zillow"

    await asset_service.delete_valuation(uow, family_id, asset.id, valuation.id)
    assert uow.store.rows(AssetValuation) == []


async def test_duplicate_valuation_date_is_409(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    await asset_service.add_valuation(uow, family_id, asset.id, as_of_date=date(2024, 1, 1), value_cents=1, note=None)

    status = await _status(
        asset_service.add_valuation(uow, family_id, asset.id, as_of_date=date(2024, 1, 1), value_cents=2, note=None)
    )

    assert status == 409


async def test_valuation_on_another_familys_asset_is_404(uow, family_id) -> None:
    other = await _asset(uow, uuid.uuid4())

    status = await _status(
        asset_service.add_valuation(uow, family_id, other.id, as_of_date=date(2024, 1, 1), value_cents=1, note=None)
    )

    assert status == 404


# ---------------------------------------------------------------------------
# contributions
# ---------------------------------------------------------------------------


async def test_contribution_crud(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    created = await asset_service.add_contribution(
        uow,
        family_id,
        asset.id,
        fields={
            "contribution_date": date(2021, 5, 1),
            "amount_cents": 1200000,
            "role": "improvement",
            "description": "Kitchen",
        },
    )
    updated = await asset_service.update_contribution(
        uow, family_id, asset.id, created.id, fields={"amount_cents": 1300000, "role": "maintenance"}
    )

    assert updated.amount_cents == 1300000 and updated.role == "maintenance" and updated.description == "Kitchen"

    await asset_service.delete_contribution(uow, family_id, asset.id, created.id)
    assert uow.store.rows(AssetContribution) == []


async def test_update_unknown_contribution_is_404(uow, family_id) -> None:
    asset = await _asset(uow, family_id)

    status = await _status(
        asset_service.update_contribution(uow, family_id, asset.id, uuid.uuid4(), fields={"amount_cents": 1})
    )

    assert status == 404


# ---------------------------------------------------------------------------
# linked expenses
# ---------------------------------------------------------------------------


async def test_list_linked_expenses_newest_first_and_only_this_asset(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    other = await _asset(uow, family_id, name="Other")
    category = make_category(family_id, "Home")
    user = make_user()
    old = make_expense(family_id, category.id, user_id=user.id, expense_date=date(2026, 1, 5), year_month="2026-01")
    new = make_expense(family_id, category.id, user_id=user.id, expense_date=date(2026, 3, 5), year_month="2026-03")
    elsewhere = make_expense(family_id, category.id, user_id=user.id)
    for expense, target in ((old, asset), (new, asset), (elsewhere, other)):
        expense.asset_id, expense.asset_role = target.id, "maintenance"
    await seed(uow, category, user, old, new, elsewhere)

    expenses = await asset_service.list_linked_expenses(uow, family_id, asset.id)

    assert [e.id for e in expenses] == [new.id, old.id]


# ---------------------------------------------------------------------------
# batch loading (the list endpoint must not query per asset)
# ---------------------------------------------------------------------------


async def test_load_details_groups_children_by_asset_in_the_given_order(uow, family_id) -> None:
    first = await _asset(uow, family_id, name="First")
    second = await _asset(uow, family_id, name="Second")
    bare = await _asset(uow, family_id, name="Bare")
    await asset_service.upsert_loan(uow, family_id, first.id, fields=dict(LOAN))
    await asset_service.add_correction(uow, family_id, first.id, as_of_date=date(2023, 1, 1), balance_cents=1)
    await asset_service.add_valuation(uow, family_id, second.id, as_of_date=date(2024, 1, 1), value_cents=2, note=None)
    await asset_service.add_valuation(uow, family_id, first.id, as_of_date=date(2025, 1, 1), value_cents=3, note=None)
    await asset_service.add_valuation(uow, family_id, first.id, as_of_date=date(2024, 1, 1), value_cents=4, note=None)
    await asset_service.add_contribution(
        uow,
        family_id,
        second.id,
        fields={"contribution_date": date(2021, 1, 1), "amount_cents": 5, "role": "improvement"},
    )

    details = await asset_service.load_details(uow, [second, bare, first])

    assert [d.asset.name for d in details] == ["Second", "Bare", "First"]
    by_name = {d.asset.name: d for d in details}
    assert by_name["First"].loan is not None and [c.balance_cents for c in by_name["First"].corrections] == [1]
    assert [v.value_cents for v in by_name["First"].valuations] == [4, 3]  # oldest as_of_date first
    assert [v.value_cents for v in by_name["Second"].valuations] == [2]
    assert [c.amount_cents for c in by_name["Second"].contributions] == [5]
    assert by_name["Second"].loan is None and by_name["Second"].corrections == []
    assert by_name["Bare"] == asset_service.AssetDetailData(bare, None, [], [], [])


async def test_load_details_with_no_assets_is_empty(uow) -> None:
    assert await asset_service.load_details(uow, []) == []


async def test_asset_expense_links_are_a_light_projection_scoped_to_family_and_assets(uow, family_id) -> None:
    asset = await _asset(uow, family_id)
    other = await _asset(uow, family_id, name="Other")
    category = make_category(family_id, "Home")
    user = make_user()
    mine = make_expense(family_id, category.id, user_id=user.id, amount_cents=700, expense_date=date(2026, 3, 5))
    mine.asset_id, mine.asset_role = asset.id, "maintenance"
    theirs = make_expense(family_id, category.id, user_id=user.id)
    theirs.asset_id, theirs.asset_role = other.id, "improvement"
    unlinked = make_expense(family_id, category.id, user_id=user.id)
    await seed(uow, category, user, mine, theirs, unlinked)

    links = await uow.expenses.list_asset_links(family_id, [asset.id])

    assert links == [AssetExpenseLink(asset.id, date(2026, 3, 5), 700, "maintenance", "expense")]
    assert await uow.expenses.list_asset_links(family_id, []) == []
    assert await uow.expenses.list_asset_links(uuid.uuid4(), [asset.id]) == []
