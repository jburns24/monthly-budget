"""Shared validation for linking an expense or recurring rule to an asset."""

import uuid

from fastapi import HTTPException

from app.ports.unit_of_work import UnitOfWork


class _Unset:
    """Type of :data:`UNSET`."""

    def __repr__(self) -> str:
        return "UNSET"


# "Not provided", as distinct from an explicit ``None`` (which clears the link).
UNSET = _Unset()


async def resolve_asset_link(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    *,
    entry_type: str,
    asset_id: uuid.UUID | None,
    asset_role: str | None,
) -> tuple[uuid.UUID | None, str | None]:
    """Validate an ``(asset_id, asset_role)`` pair and return it.

    Raises HTTPException(422) when a role has no asset, an asset has no role, or the entry
    is income; HTTPException(404) when the asset does not exist in ``family_id``.
    """
    if asset_id is None:
        if asset_role is not None:
            raise HTTPException(status_code=422, detail="asset_role requires asset_id")
        return None, None
    if entry_type != "expense":
        raise HTTPException(status_code=422, detail="Only expenses can be linked to an asset")
    if asset_role is None:
        raise HTTPException(status_code=422, detail="asset_role is required when asset_id is set")
    if await uow.assets.get_in_family(asset_id, family_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset_id, asset_role


async def merge_asset_link(
    uow: UnitOfWork,
    family_id: uuid.UUID,
    *,
    entry_type: str,
    current_id: uuid.UUID | None,
    current_role: str | None,
    new_id: uuid.UUID | None | _Unset = UNSET,
    new_role: str | None | _Unset = UNSET,
) -> tuple[uuid.UUID | None, str | None]:
    """Apply a partial update to an existing link and validate the result.

    ``UNSET`` leaves a part alone; ``None`` clears it. Clearing the asset also clears the
    role unless a role is supplied alongside (which then fails validation).
    """
    asset_id = current_id if isinstance(new_id, _Unset) else new_id
    if isinstance(new_role, _Unset):
        asset_role = None if asset_id is None else current_role
    else:
        asset_role = new_role
    return await resolve_asset_link(uow, family_id, entry_type=entry_type, asset_id=asset_id, asset_role=asset_role)
