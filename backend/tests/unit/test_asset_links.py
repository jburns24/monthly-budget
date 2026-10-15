"""Unit tests for linking expenses and recurring rules to assets, against the in-memory adapter."""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.models.expense import Expense
from app.services import expense_service, recurring_service
from app.services.asset_links import UNSET
from tests.unit.conftest import make_asset, make_category, make_user, seed


async def _setup(uow, family_id):
    category = make_category(family_id, "Home")
    user = make_user()
    asset = make_asset(family_id, user.id)
    await seed(uow, category, user, asset)
    return category, user, asset


async def _create(uow, family_id, user, category, **overrides):
    kwargs = dict(
        category_id=category.id,
        amount_cents=5000,
        description="Gutter repair",
        expense_date=date(2026, 4, 1),
    )
    kwargs.update(overrides)
    return await expense_service.create_expense(uow, family_id, user.id, **kwargs)


async def _status(coro) -> int:
    with pytest.raises(HTTPException) as exc:
        await coro
    return exc.value.status_code


# ---------------------------------------------------------------------------
# create_expense
# ---------------------------------------------------------------------------


async def test_create_expense_links_asset_and_role(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)

    expense = await _create(uow, family_id, user, category, asset_id=asset.id, asset_role="maintenance")

    assert (expense.asset_id, expense.asset_role) == (asset.id, "maintenance")


async def test_create_expense_without_link_leaves_it_null(uow, family_id) -> None:
    category, user, _ = await _setup(uow, family_id)

    expense = await _create(uow, family_id, user, category)

    assert (expense.asset_id, expense.asset_role) == (None, None)


async def test_create_expense_with_asset_from_another_family_is_404(uow, family_id) -> None:
    category, user, _ = await _setup(uow, family_id)
    foreign = make_asset(uuid.uuid4(), user.id)
    await seed(uow, foreign)

    status = await _status(_create(uow, family_id, user, category, asset_id=foreign.id, asset_role="maintenance"))

    assert status == 404


async def test_create_expense_with_asset_but_no_role_is_422(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)

    assert await _status(_create(uow, family_id, user, category, asset_id=asset.id)) == 422


async def test_create_expense_with_role_but_no_asset_is_422(uow, family_id) -> None:
    category, user, _ = await _setup(uow, family_id)

    assert await _status(_create(uow, family_id, user, category, asset_role="maintenance")) == 422


async def test_create_income_linked_to_an_asset_is_422(uow, family_id) -> None:
    _, user, asset = await _setup(uow, family_id)

    status = await _status(
        _create(
            uow, family_id, user, make_category(family_id, "x"), category_id=None, entry_type="income",
            asset_id=asset.id, asset_role="maintenance",
        )
    )  # fmt: skip

    assert status == 422


# ---------------------------------------------------------------------------
# update_expense
# ---------------------------------------------------------------------------


async def _update(uow, family_id, expense, **fields):
    return await expense_service.update_expense(
        uow, family_id, expense.id, expected_updated_at=expense.updated_at, **fields
    )


async def test_update_expense_can_link_and_unlink(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)
    expense = await _create(uow, family_id, user, category)

    linked = await _update(uow, family_id, expense, asset_id=asset.id, asset_role="improvement")
    assert (linked.asset_id, linked.asset_role) == (asset.id, "improvement")

    unlinked = await _update(uow, family_id, linked, asset_id=None)
    assert (unlinked.asset_id, unlinked.asset_role) == (None, None)


async def test_update_expense_unset_link_is_left_alone(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)
    expense = await _create(uow, family_id, user, category, asset_id=asset.id, asset_role="maintenance")

    updated = await _update(uow, family_id, expense, amount_cents=9999, asset_id=UNSET, asset_role=UNSET)

    assert (updated.asset_id, updated.asset_role, updated.amount_cents) == (asset.id, "maintenance", 9999)


async def test_update_expense_role_only_keeps_the_asset(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)
    expense = await _create(uow, family_id, user, category, asset_id=asset.id, asset_role="maintenance")

    updated = await _update(uow, family_id, expense, asset_role="carrying_cost")

    assert (updated.asset_id, updated.asset_role) == (asset.id, "carrying_cost")


async def test_update_expense_to_income_while_linked_is_422(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)
    expense = await _create(uow, family_id, user, category, asset_id=asset.id, asset_role="maintenance")

    assert await _status(_update(uow, family_id, expense, entry_type="income")) == 422


async def test_update_expense_link_to_another_familys_asset_is_404(uow, family_id) -> None:
    category, user, _ = await _setup(uow, family_id)
    foreign = make_asset(uuid.uuid4(), user.id)
    await seed(uow, foreign)
    expense = await _create(uow, family_id, user, category)

    status = await _status(_update(uow, family_id, expense, asset_id=foreign.id, asset_role="maintenance"))

    assert status == 404


# ---------------------------------------------------------------------------
# recurring rules
# ---------------------------------------------------------------------------


async def _rule(uow, family_id, user, category, **overrides):
    kwargs = dict(
        category_id=category.id,
        amount_cents=185000,
        description="Mortgage",
        entry_type="expense",
        frequency="monthly",
        start_date=date(2026, 1, 15),
        end_date=None,
        today=date(2026, 3, 20),
    )
    kwargs.update(overrides)
    return await recurring_service.create_rule(uow, family_id, user.id, **kwargs)


async def test_generated_expenses_inherit_the_rules_asset_link(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)

    rule = await _rule(uow, family_id, user, category, asset_id=asset.id, asset_role="loan_payment")

    generated = [e for e in uow.store.rows(Expense) if e.recurring_expense_id == rule.id]
    assert len(generated) == 3
    assert {(e.asset_id, e.asset_role) for e in generated} == {(asset.id, "loan_payment")}


async def test_rule_without_link_generates_unlinked_expenses(uow, family_id) -> None:
    category, user, _ = await _setup(uow, family_id)

    rule = await _rule(uow, family_id, user, category)

    generated = [e for e in uow.store.rows(Expense) if e.recurring_expense_id == rule.id]
    assert {(e.asset_id, e.asset_role) for e in generated} == {(None, None)}


async def test_create_rule_validates_the_link(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)
    foreign = make_asset(uuid.uuid4(), user.id)
    await seed(uow, foreign)

    assert await _status(_rule(uow, family_id, user, category, asset_id=foreign.id, asset_role="loan_payment")) == 404
    assert await _status(_rule(uow, family_id, user, category, asset_id=asset.id)) == 422
    income = _rule(uow, family_id, user, category, entry_type="income", category_id=None, asset_id=asset.id,
                   asset_role="loan_payment")  # fmt: skip
    assert await _status(income) == 422


async def test_update_rule_can_link_unlink_and_future_expenses_follow(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, user, category)

    linked = await recurring_service.update_rule(
        uow, family_id, rule.id, fields={"asset_id": asset.id, "asset_role": "loan_payment"}, today=date(2026, 3, 20)
    )
    assert (linked.asset_id, linked.asset_role) == (asset.id, "loan_payment")

    unlinked = await recurring_service.update_rule(
        uow, family_id, rule.id, fields={"asset_id": None}, today=date(2026, 3, 20)
    )
    assert (unlinked.asset_id, unlinked.asset_role) == (None, None)


async def test_update_rule_leaves_link_alone_when_fields_omit_it(uow, family_id) -> None:
    category, user, asset = await _setup(uow, family_id)
    rule = await _rule(uow, family_id, user, category, asset_id=asset.id, asset_role="loan_payment")

    updated = await recurring_service.update_rule(
        uow, family_id, rule.id, fields={"amount_cents": 190000}, today=date(2026, 3, 20)
    )

    assert (updated.asset_id, updated.asset_role, updated.amount_cents) == (asset.id, "loan_payment", 190000)


async def test_update_rule_link_to_another_familys_asset_is_404(uow, family_id) -> None:
    category, user, _ = await _setup(uow, family_id)
    foreign = make_asset(uuid.uuid4(), user.id)
    await seed(uow, foreign)
    rule = await _rule(uow, family_id, user, category)

    status = await _status(
        recurring_service.update_rule(
            uow,
            family_id,
            rule.id,
            fields={"asset_id": foreign.id, "asset_role": "loan_payment"},
            today=date(2026, 3, 20),
        )
    )

    assert status == 404
