"""Unit tests for the in-memory InviteRepository. No database."""

import uuid

import pytest

from app.ports.errors import UniqueViolation
from tests.unit.conftest import make_family, make_invite, make_user, seed


async def test_flush_assigns_id(uow) -> None:
    """Postgres supplies id via a Python default; the fake must too."""
    invite = make_invite(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    assert invite.id is None

    uow.invites.add(invite)
    await uow.flush()

    assert isinstance(invite.id, uuid.UUID)


async def test_flush_applies_the_pending_status_default(uow) -> None:
    """``status`` has a Python-side default of 'pending'; the fake applies it."""
    invite = make_invite(uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), status=None)

    uow.invites.add(invite)
    await uow.flush()

    assert invite.status == "pending"


async def test_get_pending_returns_the_invite(uow) -> None:
    """get_pending scopes by id, recipient, and pending status in one read."""
    invited_user_id = uuid.uuid4()
    invite = make_invite(uuid.uuid4(), invited_user_id, uuid.uuid4())
    await seed(uow, invite)

    found = await uow.invites.get_pending(invite.id, invited_user_id)

    assert found is not None
    assert found.id == invite.id


async def test_get_pending_returns_none_for_another_users_invite(uow) -> None:
    """An invite addressed to someone else is invisible, so the service 404s."""
    invite = make_invite(uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    await seed(uow, invite)

    assert await uow.invites.get_pending(invite.id, uuid.uuid4()) is None


async def test_get_pending_returns_none_once_answered(uow) -> None:
    """Already accepted or declined invites cannot be responded to twice."""
    invited_user_id = uuid.uuid4()
    invite = make_invite(uuid.uuid4(), invited_user_id, uuid.uuid4(), status="declined")
    await seed(uow, invite)

    assert await uow.invites.get_pending(invite.id, invited_user_id) is None


async def test_get_pending_for_finds_a_duplicate_invite(uow) -> None:
    """Backs the privacy-preserving "already invited" short-circuit."""
    family_id, invited_user_id = uuid.uuid4(), uuid.uuid4()
    await seed(uow, make_invite(family_id, invited_user_id, uuid.uuid4()))

    assert await uow.invites.get_pending_for(family_id, invited_user_id) is not None


async def test_get_pending_for_is_scoped_to_the_family(uow) -> None:
    """A pending invite to a different family does not block a new one."""
    invited_user_id = uuid.uuid4()
    await seed(uow, make_invite(uuid.uuid4(), invited_user_id, uuid.uuid4()))

    assert await uow.invites.get_pending_for(uuid.uuid4(), invited_user_id) is None


async def test_list_pending_for_user_detailed_eager_loads_family_and_inviter(uow) -> None:
    """Risk (a): the router reads ``inv.family.name`` and ``inv.inviting_user.display_name``."""
    inviter = make_user(display_name="Alice")
    invitee = make_user()
    await seed(uow, inviter, invitee)
    family = make_family(inviter.id, name="The Joneses")
    await seed(uow, family)
    await seed(uow, make_invite(family.id, invitee.id, inviter.id))

    invites = await uow.invites.list_pending_for_user_detailed(invitee.id)

    assert len(invites) == 1
    assert invites[0].family.name == "The Joneses"
    assert invites[0].inviting_user.display_name == "Alice"


async def test_list_pending_for_user_detailed_excludes_answered_invites(uow) -> None:
    """Only 'pending' rows reach the invites list."""
    invitee = make_user()
    await seed(uow, invitee)
    await seed(
        uow,
        make_invite(uuid.uuid4(), invitee.id, uuid.uuid4(), status="accepted"),
        make_invite(uuid.uuid4(), invitee.id, uuid.uuid4(), status="declined"),
    )

    assert await uow.invites.list_pending_for_user_detailed(invitee.id) == []


async def test_duplicate_family_user_status_raises_unique_violation(uow) -> None:
    """The fake enforces uq_invites_family_user_status and names it in the error."""
    family_id, invited_user_id = uuid.uuid4(), uuid.uuid4()
    await seed(uow, make_invite(family_id, invited_user_id, uuid.uuid4()))
    uow.invites.add(make_invite(family_id, invited_user_id, uuid.uuid4()))

    with pytest.raises(UniqueViolation) as exc_info:
        await uow.flush()

    assert exc_info.value.constraint == "uq_invites_family_user_status"
