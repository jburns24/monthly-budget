"""Recurring expenses router: configure a schedule once, entries are reconciled on demand."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import require_family_member
from app.deps.provider import get_uow
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.user import User
from app.ports.unit_of_work import UnitOfWork
from app.schemas.recurring_expense import (
    RecurringExpenseCreate,
    RecurringExpenseListResponse,
    RecurringExpenseResponse,
    RecurringExpenseUpdate,
)
from app.services import recurring_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["recurring-expenses"])


async def _today(uow: UnitOfWork, family_id: uuid.UUID) -> date:
    family = await uow.families.get(family_id)
    assert family is not None  # guaranteed by require_family_member
    return recurring_service.family_today(family.timezone)


@router.get(
    "/families/{family_id}/recurring-expenses",
    response_model=RecurringExpenseListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_recurring_expenses(
    family_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> RecurringExpenseListResponse:
    """List every recurring rule for the family."""
    rules = await recurring_service.list_rules(uow, family_id)
    return RecurringExpenseListResponse(recurring_expenses=[RecurringExpenseResponse.model_validate(r) for r in rules])


@router.post(
    "/families/{family_id}/recurring-expenses",
    response_model=RecurringExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_recurring_expense(
    family_id: uuid.UUID,
    body: RecurringExpenseCreate,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> RecurringExpenseResponse:
    """Create a recurring rule; occurrences on or before today are generated immediately."""
    current_user, _ = membership
    rule = await recurring_service.create_rule(
        uow,
        family_id,
        current_user.id,
        category_id=body.category_id,
        amount_cents=body.amount_cents,
        description=body.description,
        entry_type=body.entry_type,
        frequency=body.frequency,
        start_date=body.start_date,
        end_date=body.end_date,
        today=await _today(uow, family_id),
    )
    return RecurringExpenseResponse.model_validate(rule)


@router.put(
    "/families/{family_id}/recurring-expenses/{rule_id}",
    response_model=RecurringExpenseResponse,
    status_code=status.HTTP_200_OK,
)
async def update_recurring_expense(
    family_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: RecurringExpenseUpdate,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> RecurringExpenseResponse:
    """Update a recurring rule. Entries it already generated are left alone."""
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    rule = await recurring_service.update_rule(
        uow, family_id, rule_id, fields=fields, today=await _today(uow, family_id)
    )
    return RecurringExpenseResponse.model_validate(rule)


@router.delete(
    "/families/{family_id}/recurring-expenses/{rule_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_recurring_expense(
    family_id: uuid.UUID,
    rule_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> dict[str, str]:
    """Delete a recurring rule. Entries it already generated stay."""
    await recurring_service.delete_rule(uow, family_id, rule_id)
    return {"message": "Recurring expense deleted"}
