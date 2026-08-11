"""Unit tests for expense Pydantic schema validators (income entry_type contract)."""

import uuid
from datetime import date, datetime, timezone
from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.expense import ExpenseCreate, ExpenseResponse, ExpenseUpdate


def _expense_create(**overrides: Any) -> ExpenseCreate:
    kwargs: dict[str, Any] = {
        "amount_cents": 1000,
        "description": "Test",
        "category_id": uuid.uuid4(),
        "expense_date": date(2026, 4, 1),
    }
    kwargs.update(overrides)
    return ExpenseCreate(**kwargs)


def test_expense_create_defaults_to_expense_entry_type() -> None:
    body = _expense_create()

    assert body.entry_type == "expense"
    assert body.is_starting_balance is False


def test_expense_create_requires_category_for_expense() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _expense_create(category_id=None)

    assert "category" in str(exc_info.value).lower()


def test_expense_create_income_forbids_category() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _expense_create(entry_type="income", category_id=uuid.uuid4())

    assert "category" in str(exc_info.value).lower()


def test_expense_create_income_allows_null_category() -> None:
    body = _expense_create(entry_type="income", category_id=None)

    assert body.entry_type == "income"
    assert body.category_id is None


def test_expense_create_starting_balance_implies_income() -> None:
    body = _expense_create(is_starting_balance=True, category_id=None)

    assert body.entry_type == "income"
    assert body.is_starting_balance is True


def test_expense_create_starting_balance_rejects_expense_entry_type() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _expense_create(
            entry_type="expense",
            is_starting_balance=True,
            category_id=uuid.uuid4(),
        )

    assert "starting" in str(exc_info.value).lower() or "income" in str(exc_info.value).lower()


def test_expense_update_income_forbids_category() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExpenseUpdate(
            entry_type="income",
            category_id=uuid.uuid4(),
            expected_updated_at=datetime.now(tz=timezone.utc),
        )

    assert "category" in str(exc_info.value).lower()


def test_expense_update_expense_requires_category_when_entry_type_set() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ExpenseUpdate(
            entry_type="expense",
            category_id=None,
            expected_updated_at=datetime.now(tz=timezone.utc),
        )

    assert "category" in str(exc_info.value).lower()


def test_expense_response_allows_null_category_for_income() -> None:
    response = ExpenseResponse.model_validate(
        {
            "id": uuid.uuid4(),
            "family_id": uuid.uuid4(),
            "category": None,
            "user": {"id": uuid.uuid4(), "display_name": "Ada"},
            "amount_cents": 5000,
            "description": "Paycheck",
            "expense_date": date(2026, 4, 1),
            "created_at": datetime.now(tz=timezone.utc),
            "updated_at": datetime.now(tz=timezone.utc),
            "entry_type": "income",
            "is_starting_balance": False,
        }
    )

    assert response.entry_type == "income"
    assert response.category is None
    assert response.is_starting_balance is False
