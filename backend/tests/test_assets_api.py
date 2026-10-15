"""API + Postgres tests for the assets endpoints and linking expenses/recurring rules to assets."""

import uuid
from collections.abc import AsyncGenerator
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.database import get_db
from app.models.asset import Asset, AssetContribution, AssetLoan, AssetLoanBalanceCorrection, AssetValuation
from app.models.expense import Expense
from app.models.family_member import FamilyMember
from app.models.recurring_expense import RecurringExpense
from tests.conftest import (
    _TEST_JWT_SECRET,
    create_test_asset,
    create_test_category,
    create_test_expense,
    create_test_family,
    create_test_user,
)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """NullPool async session with per-test rollback for isolation."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session = AsyncSession(engine, expire_on_commit=False)
    await session.begin()
    try:
        yield session
    finally:
        await session.rollback()
        await session.close()
    await engine.dispose()


@pytest.fixture(autouse=True)
def patch_jwt_secret():
    with patch("app.services.jwt_service.settings") as mock_settings:
        mock_settings.jwt_secret = _TEST_JWT_SECRET
        yield


def override_get_db(session: AsyncSession):
    async def _override() -> AsyncGenerator[AsyncSession, None]:
        yield session

    return _override


@pytest.fixture
def app_with_db(db_session: AsyncSession):
    from app.main import app

    app.dependency_overrides[get_db] = override_get_db(db_session)
    yield app
    app.dependency_overrides.pop(get_db, None)


HOUSE_BODY = {
    "name": "Maple St",
    "asset_type": "house",
    "purchase_date": "2020-06-01",
    "purchase_price_cents": 40000000,
    "down_payment_cents": 8000000,
    "closing_costs_cents": 600000,
    "address_line1": "12 Maple St",
    "city": "Raleigh",
    "state": "nc",
    "zip_code": "27601",
}

LOAN_BODY = {
    "original_amount_cents": 32000000,
    "annual_interest_rate": 0.0625,
    "term_months": 360,
    "first_payment_date": "2020-07-01",
    "escrow_monthly_cents": 40000,
}


async def _admin_family(db_session):
    admin = await create_test_user(db_session, display_name="Admin")
    family, _ = await create_test_family(db_session, admin)
    return admin, family


async def _member(db_session, family) -> "object":
    member_user = await create_test_user(db_session, display_name="Member")
    db_session.add(
        FamilyMember(
            id=uuid.uuid4(),
            family_id=family.id,
            user_id=member_user.id,
            role="member",
            joined_at=datetime.now(tz=timezone.utc),
        )
    )
    await db_session.flush()
    return member_user


# ---------------------------------------------------------------------------
# create / read
# ---------------------------------------------------------------------------


async def test_admin_creates_house_with_loan_and_reads_it_back(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)

    async with authenticated_client(admin) as client:
        resp = await client.post(f"/api/families/{family.id}/assets", json={**HOUSE_BODY, "loan": LOAN_BODY})
        assert resp.status_code == 201
        created = resp.json()
        fetched = (await client.get(f"/api/families/{family.id}/assets/{created['id']}")).json()

    assert created["name"] == "Maple St" and created["state"] == "NC" and created["is_sold"] is False
    assert created["family_id"] == str(family.id) and created["created_by_user_id"] == str(admin.id)
    assert created["loan"]["original_amount_cents"] == 32000000
    assert created["loan"]["annual_interest_rate"] == 0.0625  # a JSON number, not a Decimal string
    assert created["loan"]["monthly_payment_cents"] is None and created["loan"]["escrow_monthly_cents"] == 40000
    assert created["corrections"] == [] and created["valuations"] == [] and created["contributions"] == []
    assert fetched == created


async def test_create_house_requires_state_and_zip(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    body = {k: v for k, v in HOUSE_BODY.items() if k not in ("state", "zip_code")}

    async with authenticated_client(admin) as client:
        resp = await client.post(f"/api/families/{family.id}/assets", json=body)

    assert resp.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"asset_type": "boat"},
        {"name": "   "},
        {"zip_code": "2760"},
        {"state": "North Carolina"},
        {"purchase_price_cents": -1},
        {"loan": {**LOAN_BODY, "term_months": 0}},
        {"loan": {**LOAN_BODY, "annual_interest_rate": 2}},
    ],
)
async def test_create_asset_rejects_bad_input(db_session, app_with_db, authenticated_client, overrides) -> None:
    admin, family = await _admin_family(db_session)

    async with authenticated_client(admin) as client:
        resp = await client.post(f"/api/families/{family.id}/assets", json={**HOUSE_BODY, **overrides})

    assert resp.status_code == 422


async def test_vehicle_needs_no_address_and_keeps_its_depreciation_rate(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _admin_family(db_session)
    body = {
        "name": "Civic",
        "asset_type": "vehicle",
        "purchase_date": "2022-01-15",
        "purchase_price_cents": 2500000,
        "annual_depreciation_rate": 0.12,
    }

    async with authenticated_client(admin) as client:
        resp = await client.post(f"/api/families/{family.id}/assets", json=body)

    assert resp.status_code == 201
    assert resp.json()["annual_depreciation_rate"] == 0.12 and resp.json()["state"] is None


async def test_list_returns_only_this_familys_assets(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    other_admin, other_family = await _admin_family(db_session)
    mine = await create_test_asset(db_session, family, admin, name="Mine")
    await create_test_asset(db_session, other_family, other_admin, name="Theirs")

    async with authenticated_client(admin) as client:
        resp = await client.get(f"/api/families/{family.id}/assets")

    assert resp.status_code == 200
    assert [a["id"] for a in resp.json()["assets"]] == [str(mine.id)]


async def test_asset_in_another_family_is_404_and_non_member_is_404(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _admin_family(db_session)
    other_admin, other_family = await _admin_family(db_session)
    theirs = await create_test_asset(db_session, other_family, other_admin)

    async with authenticated_client(admin) as client:
        cross_family = await client.get(f"/api/families/{family.id}/assets/{theirs.id}")
        non_member = await client.get(f"/api/families/{other_family.id}/assets/{theirs.id}")

    assert cross_family.status_code == 404
    assert non_member.status_code == 404


# ---------------------------------------------------------------------------
# permissions
# ---------------------------------------------------------------------------


async def test_member_can_read_but_not_write(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    member = await _member(db_session, family)
    asset = await create_test_asset(db_session, family, admin)
    base = f"/api/families/{family.id}/assets"
    sub = f"{base}/{asset.id}"
    some_id = uuid.uuid4()

    async with authenticated_client(member) as client:
        reads = [await client.get(base), await client.get(sub), await client.get(f"{sub}/expenses")]
        writes = [
            await client.post(base, json=HOUSE_BODY),
            await client.put(sub, json={"name": "x"}),
            await client.delete(sub),
            await client.post(
                f"{sub}/sell", json={"sold_date": "2025-01-01", "sale_price_cents": 1, "selling_costs_cents": 0}
            ),
            await client.delete(f"{sub}/sell"),
            await client.put(f"{sub}/loan", json=LOAN_BODY),
            await client.delete(f"{sub}/loan"),
            await client.post(f"{sub}/loan/corrections", json={"as_of_date": "2024-01-01", "balance_cents": 1}),
            await client.delete(f"{sub}/loan/corrections/{some_id}"),
            await client.post(f"{sub}/valuations", json={"as_of_date": "2024-01-01", "value_cents": 1}),
            await client.delete(f"{sub}/valuations/{some_id}"),
            await client.post(
                f"{sub}/contributions",
                json={"contribution_date": "2024-01-01", "amount_cents": 1, "role": "improvement"},
            ),
            await client.put(f"{sub}/contributions/{some_id}", json={"amount_cents": 2}),
            await client.delete(f"{sub}/contributions/{some_id}"),
        ]

    assert [r.status_code for r in reads] == [200, 200, 200]
    assert [r.status_code for r in writes] == [403] * len(writes)


async def test_member_can_link_an_expense_to_an_asset(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    member = await _member(db_session, family)
    asset = await create_test_asset(db_session, family, admin)
    category = await create_test_category(db_session, family, name="Home")

    async with authenticated_client(member) as client:
        resp = await client.post(
            f"/api/families/{family.id}/expenses",
            json={
                "amount_cents": 25000,
                "category_id": str(category.id),
                "expense_date": "2026-04-02",
                "asset_id": str(asset.id),
                "asset_role": "maintenance",
            },
        )

    assert resp.status_code == 201
    assert resp.json()["asset_id"] == str(asset.id) and resp.json()["asset_role"] == "maintenance"


# ---------------------------------------------------------------------------
# update / delete
# ---------------------------------------------------------------------------


async def test_update_changes_only_sent_fields(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin, city="Raleigh", address_line1="1 Main")

    async with authenticated_client(admin) as client:
        resp = await client.put(
            f"/api/families/{family.id}/assets/{asset.id}", json={"name": "Renamed", "address_line1": None}
        )
        empty = await client.put(f"/api/families/{family.id}/assets/{asset.id}", json={})
        null_name = await client.put(f"/api/families/{family.id}/assets/{asset.id}", json={"name": None})

    assert resp.status_code == 200
    body = resp.json()
    assert (body["name"], body["address_line1"], body["city"]) == ("Renamed", None, "Raleigh")
    assert empty.status_code == 400
    assert null_name.status_code == 422


async def test_delete_unlinks_expenses_and_recurring_rules_and_removes_children(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    survivor = await create_test_asset(db_session, family, admin, name="Survivor")
    category = await create_test_category(db_session, family, name="Home")
    linked = await create_test_expense(db_session, family, admin, category, asset_id=asset.id, asset_role="maintenance")
    kept = await create_test_expense(
        db_session, family, admin, category, asset_id=survivor.id, asset_role="improvement"
    )
    rule = RecurringExpense(
        id=uuid.uuid4(),
        family_id=family.id,
        user_id=admin.id,
        category_id=category.id,
        amount_cents=185000,
        description="Mortgage",
        frequency="monthly",
        start_date=date(2026, 1, 1),
        next_due_date=date(2026, 2, 1),
        asset_id=asset.id,
        asset_role="loan_payment",
    )
    db_session.add(rule)
    loan = AssetLoan(
        asset_id=asset.id,
        original_amount_cents=100,
        annual_interest_rate=0.05,
        term_months=12,
        first_payment_date=date(2020, 7, 1),
    )
    db_session.add(loan)
    await db_session.flush()
    db_session.add_all(
        [
            AssetLoanBalanceCorrection(loan_id=loan.id, as_of_date=date(2021, 1, 1), balance_cents=50),
            AssetValuation(asset_id=asset.id, as_of_date=date(2021, 1, 1), value_cents=1),
            AssetContribution(
                asset_id=asset.id, contribution_date=date(2021, 1, 1), amount_cents=1, role="improvement"
            ),
        ]
    )
    await db_session.flush()

    async with authenticated_client(admin) as client:
        resp = await client.delete(f"/api/families/{family.id}/assets/{asset.id}")
        gone = await client.get(f"/api/families/{family.id}/assets/{asset.id}")

    assert resp.status_code == 204 and gone.status_code == 404
    await db_session.refresh(linked)
    await db_session.refresh(rule)
    await db_session.refresh(kept)
    assert (linked.asset_id, linked.asset_role) == (None, None)
    assert (rule.asset_id, rule.asset_role) == (None, None)
    assert (kept.asset_id, kept.asset_role) == (survivor.id, "improvement")
    for model in (AssetLoan, AssetLoanBalanceCorrection, AssetValuation, AssetContribution):
        assert (await db_session.execute(select(model))).scalars().all() == []


# ---------------------------------------------------------------------------
# sell / un-sell
# ---------------------------------------------------------------------------


async def test_sell_then_unsell(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    url = f"/api/families/{family.id}/assets/{asset.id}"
    sale = {"sold_date": "2025-03-01", "sale_price_cents": 50000000, "selling_costs_cents": 300000}

    async with authenticated_client(admin) as client:
        sold = await client.post(f"{url}/sell", json=sale)
        again = await client.post(f"{url}/sell", json=sale)
        unsold = await client.delete(f"{url}/sell")
        unsold_again = await client.delete(f"{url}/sell")

    assert sold.status_code == 200
    assert (sold.json()["is_sold"], sold.json()["sold_date"], sold.json()["sale_price_cents"]) == (
        True,
        "2025-03-01",
        50000000,
    )
    assert sold.json()["selling_costs_cents"] == 300000
    assert again.status_code == 409
    assert unsold.status_code == 200 and unsold.json()["is_sold"] is False
    assert unsold.json()["sold_date"] is None and unsold.json()["sale_price_cents"] is None
    assert unsold_again.status_code == 409


async def test_sell_on_a_future_date_is_422(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    tomorrow = date.today() + timedelta(days=2)  # beyond any timezone's "today"

    async with authenticated_client(admin) as client:
        resp = await client.post(
            f"/api/families/{family.id}/assets/{asset.id}/sell",
            json={"sold_date": tomorrow.isoformat(), "sale_price_cents": 1},
        )

    assert resp.status_code == 422


async def test_sell_before_purchase_is_422(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)

    async with authenticated_client(admin) as client:
        resp = await client.post(
            f"/api/families/{family.id}/assets/{asset.id}/sell",
            json={"sold_date": "2019-01-01", "sale_price_cents": 1},
        )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# loan, corrections, valuations, contributions
# ---------------------------------------------------------------------------


async def test_loan_upsert_and_delete(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    url = f"/api/families/{family.id}/assets/{asset.id}"

    async with authenticated_client(admin) as client:
        created = await client.put(f"{url}/loan", json=LOAN_BODY)
        updated = await client.put(f"{url}/loan", json={**LOAN_BODY, "annual_interest_rate": 0.05, "term_months": 180})
        detail = (await client.get(url)).json()
        deleted = await client.delete(f"{url}/loan")
        missing = await client.delete(f"{url}/loan")

    assert created.status_code == 200 and updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]
    assert (detail["loan"]["annual_interest_rate"], detail["loan"]["term_months"]) == (0.05, 180)
    assert deleted.status_code == 204 and missing.status_code == 404


async def test_corrections_create_duplicate_and_delete(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    url = f"/api/families/{family.id}/assets/{asset.id}"
    body = {"as_of_date": "2023-01-01", "balance_cents": 30000000}

    async with authenticated_client(admin) as client:
        no_loan = await client.post(f"{url}/loan/corrections", json=body)
        await client.put(f"{url}/loan", json=LOAN_BODY)
        created = await client.post(f"{url}/loan/corrections", json=body)
        duplicate = await client.post(f"{url}/loan/corrections", json={**body, "balance_cents": 1})
        # The 409 must not poison the request transaction: the first correction is still there.
        detail = (await client.get(url)).json()
        deleted = await client.delete(f"{url}/loan/corrections/{created.json()['id']}")
        after = (await client.get(url)).json()

    assert no_loan.status_code == 404
    assert created.status_code == 201 and created.json()["balance_cents"] == 30000000
    assert duplicate.status_code == 409
    assert [c["balance_cents"] for c in detail["corrections"]] == [30000000]
    assert deleted.status_code == 204 and after["corrections"] == []


async def test_valuations_create_duplicate_and_delete(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    url = f"/api/families/{family.id}/assets/{asset.id}"
    body = {"as_of_date": "2024-01-01", "value_cents": 45000000, "note": "Appraisal"}

    async with authenticated_client(admin) as client:
        created = await client.post(f"{url}/valuations", json=body)
        duplicate = await client.post(f"{url}/valuations", json={**body, "value_cents": 1})
        detail = (await client.get(url)).json()
        deleted = await client.delete(f"{url}/valuations/{created.json()['id']}")
        missing = await client.delete(f"{url}/valuations/{created.json()['id']}")

    assert created.status_code == 201 and created.json()["note"] == "Appraisal"
    assert duplicate.status_code == 409
    assert [v["value_cents"] for v in detail["valuations"]] == [45000000]
    assert deleted.status_code == 204 and missing.status_code == 404


async def test_contributions_crud(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    url = f"/api/families/{family.id}/assets/{asset.id}"
    body = {"contribution_date": "2021-05-01", "amount_cents": 1200000, "role": "improvement", "description": "Kitchen"}

    async with authenticated_client(admin) as client:
        created = await client.post(f"{url}/contributions", json=body)
        cid = created.json()["id"]
        updated = await client.put(f"{url}/contributions/{cid}", json={"amount_cents": 1300000, "role": "maintenance"})
        bad_role = await client.post(f"{url}/contributions", json={**body, "role": "loan_payment"})
        null_amount = await client.put(f"{url}/contributions/{cid}", json={"amount_cents": None})
        empty = await client.put(f"{url}/contributions/{cid}", json={})
        deleted = await client.delete(f"{url}/contributions/{cid}")
        missing = await client.put(f"{url}/contributions/{cid}", json={"amount_cents": 5})

    assert created.status_code == 201
    assert updated.status_code == 200
    assert (updated.json()["amount_cents"], updated.json()["role"], updated.json()["description"]) == (
        1300000,
        "maintenance",
        "Kitchen",
    )
    assert bad_role.status_code == 422 and null_amount.status_code == 422 and empty.status_code == 400
    assert deleted.status_code == 204 and missing.status_code == 404


# ---------------------------------------------------------------------------
# expense linking
# ---------------------------------------------------------------------------


def _expense_body(category, **extra):
    return {"amount_cents": 25000, "category_id": str(category.id), "expense_date": "2026-04-02", **extra}


async def test_expense_link_validation(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    other_admin, other_family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    foreign = await create_test_asset(db_session, other_family, other_admin)
    category = await create_test_category(db_session, family, name="Home")
    url = f"/api/families/{family.id}/expenses"

    async with authenticated_client(admin) as client:
        ok = await client.post(url, json=_expense_body(category, asset_id=str(asset.id), asset_role="loan_payment"))
        no_role = await client.post(url, json=_expense_body(category, asset_id=str(asset.id)))
        role_only = await client.post(url, json=_expense_body(category, asset_role="maintenance"))
        bad_role = await client.post(url, json=_expense_body(category, asset_id=str(asset.id), asset_role="gift"))
        income = await client.post(
            url,
            json={
                "amount_cents": 1000,
                "expense_date": "2026-04-02",
                "entry_type": "income",
                "asset_id": str(asset.id),
                "asset_role": "maintenance",
            },
        )
        wrong_family = await client.post(
            url, json=_expense_body(category, asset_id=str(foreign.id), asset_role="maintenance")
        )
        unknown = await client.post(
            url, json=_expense_body(category, asset_id=str(uuid.uuid4()), asset_role="maintenance")
        )

    assert ok.status_code == 201
    assert (no_role.status_code, role_only.status_code, bad_role.status_code, income.status_code) == (422,) * 4
    assert wrong_family.status_code == 404 and unknown.status_code == 404


async def test_expense_update_links_unlinks_and_leaves_alone(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    category = await create_test_category(db_session, family, name="Home")
    expense = await create_test_expense(
        db_session, family, admin, category, expense_date=date.today(), year_month=date.today().strftime("%Y-%m")
    )

    async def put(client, **fields):
        current = (await client.get(f"/api/families/{family.id}/expenses/{expense.id}")).json()
        return await client.put(
            f"/api/families/{family.id}/expenses/{expense.id}",
            json={"expected_updated_at": current["updated_at"], **fields},
        )

    async with authenticated_client(admin) as client:
        linked = await put(client, asset_id=str(asset.id), asset_role="improvement")
        untouched = await put(client, description="renamed")
        role_only = await put(client, asset_role="carrying_cost")
        income = await put(client, entry_type="income")
        unlinked = await put(client, asset_id=None)

    assert (linked.json()["asset_id"], linked.json()["asset_role"]) == (str(asset.id), "improvement")
    assert (untouched.json()["asset_id"], untouched.json()["asset_role"]) == (str(asset.id), "improvement")
    assert role_only.json()["asset_role"] == "carrying_cost"
    assert income.status_code == 422
    assert (unlinked.json()["asset_id"], unlinked.json()["asset_role"]) == (None, None)


async def test_linked_expenses_endpoint_lists_newest_first(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    member = await _member(db_session, family)
    asset = await create_test_asset(db_session, family, admin)
    other = await create_test_asset(db_session, family, admin, name="Other")
    category = await create_test_category(db_session, family, name="Home")
    kwargs = {"asset_role": "maintenance"}
    old = await create_test_expense(
        db_session,
        family,
        admin,
        category,
        asset_id=asset.id,
        expense_date=date(2026, 1, 5),
        year_month="2026-01",
        **kwargs,
    )
    new = await create_test_expense(
        db_session,
        family,
        admin,
        category,
        asset_id=asset.id,
        expense_date=date(2026, 3, 5),
        year_month="2026-03",
        **kwargs,
    )
    await create_test_expense(db_session, family, admin, category, asset_id=other.id, **kwargs)
    await create_test_expense(db_session, family, admin, category)

    async with authenticated_client(member) as client:
        resp = await client.get(f"/api/families/{family.id}/assets/{asset.id}/expenses")
        missing = await client.get(f"/api/families/{family.id}/assets/{uuid.uuid4()}/expenses")

    assert resp.status_code == 200
    body = resp.json()["expenses"]
    assert [e["id"] for e in body] == [str(new.id), str(old.id)]
    assert body[0]["category"]["name"] == "Home" and body[0]["asset_role"] == "maintenance"
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# recurring inheritance
# ---------------------------------------------------------------------------


async def test_recurring_rule_links_and_generated_expenses_inherit(
    db_session, app_with_db, authenticated_client
) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    category = await create_test_category(db_session, family, name="Mortgage")
    start = date.today() - timedelta(days=45)

    async with authenticated_client(admin) as client:
        resp = await client.post(
            f"/api/families/{family.id}/recurring-expenses",
            json={
                "amount_cents": 185000,
                "description": "Mortgage",
                "category_id": str(category.id),
                "frequency": "weekly",
                "start_date": start.isoformat(),
                "asset_id": str(asset.id),
                "asset_role": "loan_payment",
            },
        )
        linked_expenses = await client.get(f"/api/families/{family.id}/assets/{asset.id}/expenses")

    assert resp.status_code == 201
    assert (resp.json()["asset_id"], resp.json()["asset_role"]) == (str(asset.id), "loan_payment")
    generated = linked_expenses.json()["expenses"]
    assert len(generated) >= 6
    assert {e["asset_role"] for e in generated} == {"loan_payment"}
    assert all(e["recurring_expense_id"] == resp.json()["id"] for e in generated)


async def test_recurring_rule_link_validation_and_update(db_session, app_with_db, authenticated_client) -> None:
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    category = await create_test_category(db_session, family, name="Mortgage")
    url = f"/api/families/{family.id}/recurring-expenses"
    base = {
        "amount_cents": 185000,
        "category_id": str(category.id),
        "frequency": "monthly",
        "start_date": (date.today() + timedelta(days=10)).isoformat(),
    }

    async with authenticated_client(admin) as client:
        no_role = await client.post(url, json={**base, "asset_id": str(asset.id)})
        income = await client.post(
            url,
            json={
                "amount_cents": 1,
                "entry_type": "income",
                "frequency": "monthly",
                "start_date": base["start_date"],
                "asset_id": str(asset.id),
                "asset_role": "maintenance",
            },
        )
        wrong = await client.post(url, json={**base, "asset_id": str(uuid.uuid4()), "asset_role": "loan_payment"})
        rule = (await client.post(url, json=base)).json()
        linked = await client.put(f"{url}/{rule['id']}", json={"asset_id": str(asset.id), "asset_role": "loan_payment"})
        renamed = await client.put(f"{url}/{rule['id']}", json={"amount_cents": 190000})
        unlinked = await client.put(f"{url}/{rule['id']}", json={"asset_id": None})

    assert (no_role.status_code, income.status_code) == (422, 422) and wrong.status_code == 404
    assert (linked.json()["asset_id"], linked.json()["asset_role"]) == (str(asset.id), "loan_payment")
    assert (renamed.json()["asset_id"], renamed.json()["asset_role"]) == (str(asset.id), "loan_payment")
    assert (unlinked.json()["asset_id"], unlinked.json()["asset_role"]) == (None, None)


# ---------------------------------------------------------------------------
# schema constraints
# ---------------------------------------------------------------------------


async def test_a_role_without_an_asset_is_rejected_by_the_database(db_session) -> None:
    admin, family = await _admin_family(db_session)
    category = await create_test_category(db_session, family, name="Home")

    with pytest.raises(IntegrityError, match="ck_expenses_asset_role_requires_asset"):
        await create_test_expense(db_session, family, admin, category, asset_role="maintenance")


async def test_sold_fields_must_be_set_together(db_session) -> None:
    admin, family = await _admin_family(db_session)

    with pytest.raises(IntegrityError, match="ck_assets_sold_fields"):
        await create_test_asset(db_session, family, admin, sale_price_cents=1)


async def test_deleting_a_family_with_linked_expenses_succeeds(db_session) -> None:
    """The SET NULL on asset_id must not trip the role check while the family cascades away."""
    admin, family = await _admin_family(db_session)
    asset = await create_test_asset(db_session, family, admin)
    category = await create_test_category(db_session, family, name="Home")
    await create_test_expense(db_session, family, admin, category, asset_id=asset.id, asset_role="maintenance")

    await db_session.execute(text("DELETE FROM families WHERE id = :id"), {"id": family.id})

    assert (await db_session.execute(select(Asset).where(Asset.family_id == family.id))).scalars().all() == []
    assert (await db_session.execute(select(Expense).where(Expense.family_id == family.id))).scalars().all() == []
