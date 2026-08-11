"""Tests for the in-memory store's model-spec derivation. No database.

The store does not restate what a model declares — it reads the mapper. These
tests pin the translation from SQLAlchemy metadata to flush-time behaviour, and
in particular pin the two places it can't be fully mechanical: a ``server_default``
is opaque DDL that needs a hand-written Python stand-in, and a SQL-expression
default has none at all. Both must fail loudly rather than quietly produce None.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import Column, String, text

from app.adapters.memory.store import UniqueIndex, _server_default, model_spec
from app.models.category import Category
from app.models.expense import Expense


def test_python_side_defaults_are_derived_from_the_model() -> None:
    """Columns with ``default=`` need no hand-written entry."""
    defaults = model_spec(Category).defaults

    assert isinstance(defaults["id"](), uuid.UUID)
    assert defaults["sort_order"]() == 0
    assert defaults["is_active"]() is True


def test_scalar_defaults_of_other_models_are_derived_too() -> None:
    """Derivation is generic, not special-cased for Category."""
    assert model_spec(Expense).defaults["description"]() == ""


def test_server_defaults_get_a_timezone_aware_python_stand_in() -> None:
    """created_at has no Python default at all, yet CategoryResponse requires it."""
    created_at = model_spec(Category).defaults["created_at"]()

    assert isinstance(created_at, datetime)
    assert created_at.tzinfo is not None


def test_every_auto_filled_column_is_covered() -> None:
    """Nothing the database would populate is left as None by flush()."""
    assert set(model_spec(Category).defaults) == {"id", "sort_order", "is_active", "created_at"}
    assert set(model_spec(Expense).defaults) == {
        "id",
        "description",
        "entry_type",
        "is_starting_balance",
        "created_at",
        "updated_at",
    }


def test_composite_unique_constraints_are_derived_from_the_table() -> None:
    """The constraint the fake enforces is read straight off the model."""
    assert model_spec(Category).unique == (UniqueIndex("uq_categories_family_name", ("family_id", "name")),)


def test_partial_unique_indexes_are_derived_from_the_table() -> None:
    """A boolean-column postgresql_where becomes UniqueIndex.where_field."""
    assert model_spec(Expense).unique == (
        UniqueIndex(
            "uq_expenses_starting_balance_per_family_month",
            ("family_id", "year_month"),
            where_field="is_starting_balance",
        ),
    )


def test_an_unrecognised_server_default_fails_loudly() -> None:
    """A new server_default must be given a stand-in, not silently ignored."""
    column = Column("nickname", String, server_default=text("'anonymous'"))

    with pytest.raises(LookupError, match="_SERVER_DEFAULT_SHIMS"):
        _server_default(column, Category, "nickname")


def test_specs_are_built_once_per_model() -> None:
    """The mapper walk is cached; repeated flushes must not redo it."""
    assert model_spec(Category) is model_spec(Category)
