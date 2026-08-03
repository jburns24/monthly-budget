"""Unit tests for the in-memory FamilyRepository. No database."""

import uuid

from tests.unit.conftest import make_family, make_family_member, make_user, seed


async def test_flush_assigns_id(uow) -> None:
    """Postgres supplies id via a Python default; the fake must too."""
    family = make_family(uuid.uuid4())
    assert family.id is None

    uow.families.add(family)
    await uow.flush()

    assert isinstance(family.id, uuid.UUID)


async def test_get_returns_the_family(uow) -> None:
    """get is the plain primary-key read used by the grace-period checks."""
    family = make_family(uuid.uuid4(), name="The Joneses")
    await seed(uow, family)

    found = await uow.families.get(family.id)

    assert found is not None
    assert found.name == "The Joneses"


async def test_get_returns_none_for_an_unknown_id(uow) -> None:
    """A missing family is None, so the service can raise its own 404."""
    assert await uow.families.get(uuid.uuid4()) is None


async def test_get_with_members_eager_loads_members_and_their_users(uow) -> None:
    """Risk (a): ``_family_to_response`` walks ``family.members[*].user.email``.

    The SQLAlchemy adapter gets this from ``joinedload(members).joinedload(user)``.
    There is no session here to lazy-load from, so the fake has to populate both
    hops explicitly or the router would read ``None`` instead of raising.
    """
    owner = make_user(email="owner@example.com")
    other = make_user(email="other@example.com")
    await seed(uow, owner, other)
    family = make_family(owner.id)
    await seed(uow, family)
    await seed(
        uow,
        make_family_member(family.id, owner.id, role="admin"),
        make_family_member(family.id, other.id, role="member"),
    )

    found = await uow.families.get_with_members(family.id)

    assert found is not None
    assert {m.user.email for m in found.members} == {"owner@example.com", "other@example.com"}


async def test_get_with_members_excludes_other_families_members(uow) -> None:
    """Membership rows are scoped to the family being loaded."""
    owner = make_user()
    await seed(uow, owner)
    family = make_family(owner.id)
    await seed(uow, family)
    await seed(
        uow,
        make_family_member(family.id, owner.id, role="admin"),
        make_family_member(uuid.uuid4(), uuid.uuid4()),
    )

    found = await uow.families.get_with_members(family.id)

    assert found is not None
    assert [m.user_id for m in found.members] == [owner.id]


async def test_get_with_members_returns_an_empty_list_for_a_family_with_none(uow) -> None:
    """A family with no membership rows loads with ``members == []``, not None."""
    family = make_family(uuid.uuid4())
    await seed(uow, family)

    found = await uow.families.get_with_members(family.id)

    assert found is not None
    assert found.members == []


async def test_get_with_members_returns_none_for_an_unknown_id(uow) -> None:
    """Eager loading does not change the missing-row answer."""
    assert await uow.families.get_with_members(uuid.uuid4()) is None
