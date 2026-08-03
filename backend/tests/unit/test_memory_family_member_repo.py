"""Unit tests for the in-memory FamilyMemberRepository. No database."""

import uuid

import pytest

from app.ports.errors import UniqueViolation
from tests.unit.conftest import make_family, make_family_member, make_user, seed


async def test_flush_assigns_id(uow) -> None:
    """Postgres supplies id via a Python default; the fake must too."""
    family_id, user_id = uuid.uuid4(), uuid.uuid4()
    member = make_family_member(family_id, user_id)
    assert member.id is None

    uow.members.add(member)
    await uow.flush()

    assert isinstance(member.id, uuid.UUID)


async def test_get_for_user_in_family_returns_the_member(uow) -> None:
    """get_for_user_in_family finds the membership row scoped to both ids."""
    family_id, user_id = uuid.uuid4(), uuid.uuid4()
    member = make_family_member(family_id, user_id, role="admin")
    await seed(uow, member)

    found = await uow.members.get_for_user_in_family(family_id, user_id)

    assert found is not None
    assert found.role == "admin"


async def test_get_for_user_in_family_returns_none_for_a_different_family(uow) -> None:
    """The lookup is scoped by family_id, not just user_id."""
    family_id, user_id = uuid.uuid4(), uuid.uuid4()
    await seed(uow, make_family_member(family_id, user_id))

    assert await uow.members.get_for_user_in_family(uuid.uuid4(), user_id) is None


async def test_get_any_for_user_returns_the_users_membership(uow) -> None:
    """get_any_for_user finds the single family a user belongs to."""
    family_id, user_id = uuid.uuid4(), uuid.uuid4()
    member = make_family_member(family_id, user_id)
    await seed(uow, member)

    found = await uow.members.get_any_for_user(user_id)

    assert found is not None
    assert found.family_id == family_id


async def test_get_any_for_user_returns_none_when_the_user_has_no_family(uow) -> None:
    """A user with no membership returns None, not an error."""
    assert await uow.members.get_any_for_user(uuid.uuid4()) is None


async def test_get_with_family_eager_loads_family(uow) -> None:
    """get_with_family replaces the router's ``db.refresh(membership, ['family'])``."""
    owner = make_user()
    await seed(uow, owner)
    family = make_family(owner.id, name="The Joneses")
    await seed(uow, family)
    member = make_family_member(family.id, owner.id)
    await seed(uow, member)

    found = await uow.members.get_with_family(owner.id)

    assert found is not None
    assert found.family.name == "The Joneses"


async def test_get_with_family_returns_none_without_a_membership(uow) -> None:
    """No membership means None, regardless of eager loading."""
    assert await uow.members.get_with_family(uuid.uuid4()) is None


async def test_get_with_user_eager_loads_user(uow) -> None:
    """get_with_user replaces the router's ``db.refresh(member, ['user'])``."""
    user = make_user(display_name="Bob")
    await seed(uow, user)
    family = make_family(user.id)
    await seed(uow, family)
    member = make_family_member(family.id, user.id)
    await seed(uow, member)

    found = await uow.members.get_with_user(family.id, user.id)

    assert found is not None
    assert found.user.display_name == "Bob"


async def test_get_with_user_returns_none_for_an_unknown_pair(uow) -> None:
    """An unmatched (family_id, user_id) pair is None, not an error."""
    assert await uow.members.get_with_user(uuid.uuid4(), uuid.uuid4()) is None


async def test_count_admins_counts_only_admin_members(uow) -> None:
    """count_admins is used to guard demoting/removing the last admin."""
    family_id = uuid.uuid4()
    await seed(
        uow,
        make_family_member(family_id, uuid.uuid4(), role="admin"),
        make_family_member(family_id, uuid.uuid4(), role="admin"),
        make_family_member(family_id, uuid.uuid4(), role="member"),
    )

    assert await uow.members.count_admins(family_id) == 2


async def test_count_admins_is_scoped_to_the_family(uow) -> None:
    """count_admins does not count admins of other families."""
    family_id = uuid.uuid4()
    await seed(uow, make_family_member(uuid.uuid4(), uuid.uuid4(), role="admin"))

    assert await uow.members.count_admins(family_id) == 0


async def test_delete_removes_the_row_on_flush(uow) -> None:
    """delete is staged, then applied by flush."""
    family_id, user_id = uuid.uuid4(), uuid.uuid4()
    member = make_family_member(family_id, user_id)
    await seed(uow, member)

    await uow.members.delete(member)
    await uow.flush()

    assert await uow.members.get_for_user_in_family(family_id, user_id) is None


async def test_duplicate_family_user_pair_raises_unique_violation(uow) -> None:
    """The fake enforces uq_family_members_family_user and names it in the error."""
    family_id, user_id = uuid.uuid4(), uuid.uuid4()
    await seed(uow, make_family_member(family_id, user_id))
    uow.members.add(make_family_member(family_id, user_id))

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_family_members_family_user"
