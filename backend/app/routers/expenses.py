"""Expenses router: CRUD endpoints for family expenses and budget summary."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import require_family_member
from app.deps.provider import get_uow
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.user import User
from app.ports.unit_of_work import UnitOfWork
from app.schemas.expense import (
    BudgetSummaryResponse,
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseResponse,
    ExpenseUpdate,
)
from app.services import expense_service
from app.services.grace_period import is_within_grace_period

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["expenses"])


async def _is_editable(uow: UnitOfWork, family_id: uuid.UUID, year_month: str) -> bool:
    """Whether ``year_month`` is still within the family's edit grace period.

    Every caller reaches this behind ``require_family_member``, which has already
    proved the membership row — and therefore the family — exists, so a missing
    family here is a bug rather than a 404. Assert instead of silently treating
    it as read-only.
    """
    family = await uow.families.get(family_id)
    assert family is not None  # guaranteed by require_family_member
    return is_within_grace_period(family, year_month)


@router.get(
    "/families/{family_id}/expenses",
    response_model=ExpenseListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_expenses(
    family_id: uuid.UUID,
    year_month: str = Query(..., description="Filter by month in YYYY-MM format"),
    category_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> ExpenseListResponse:
    """List paginated expenses for a family filtered by year_month."""
    expenses, total_count = await expense_service.list_expenses(
        uow,
        family_id=family_id,
        year_month=year_month,
        category_id=category_id,
        page=page,
        per_page=per_page,
    )
    return ExpenseListResponse(
        expenses=[ExpenseResponse.model_validate(e) for e in expenses],
        total_count=total_count,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/families/{family_id}/expenses",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_expense(
    family_id: uuid.UUID,
    body: ExpenseCreate,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> ExpenseResponse:
    """Create a new expense for a family (any member)."""
    current_user, _ = membership
    expense = await expense_service.create_expense(
        uow,
        family_id=family_id,
        user_id=current_user.id,
        category_id=body.category_id,
        amount_cents=body.amount_cents,
        description=body.description,
        expense_date=body.expense_date,
    )
    logger.info("expense_created_endpoint", expense_id=str(expense.id), user_id=str(current_user.id))
    return ExpenseResponse.model_validate(expense)


@router.get(
    "/families/{family_id}/expenses/{expense_id}",
    response_model=ExpenseResponse,
    status_code=status.HTTP_200_OK,
)
async def get_expense(
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> ExpenseResponse:
    """Get a single expense by ID."""
    expense = await expense_service.get_expense(uow, family_id=family_id, expense_id=expense_id)
    return ExpenseResponse.model_validate(expense)


@router.put(
    "/families/{family_id}/expenses/{expense_id}",
    response_model=ExpenseResponse,
    status_code=status.HTTP_200_OK,
)
async def update_expense(
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
    body: ExpenseUpdate,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> ExpenseResponse:
    """Update an expense with optimistic locking."""
    current_user, _ = membership

    # Fetch the expense first to know its month, then enforce grace period
    existing = await expense_service.get_expense(uow, family_id=family_id, expense_id=expense_id)
    if not await _is_editable(uow, family_id, existing.year_month):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grace period expired. Past-month expenses are read-only.",
        )

    expense = await expense_service.update_expense(
        uow,
        family_id=family_id,
        expense_id=expense_id,
        expected_updated_at=body.expected_updated_at,
        amount_cents=body.amount_cents,
        description=body.description,
        category_id=body.category_id,
        expense_date=body.expense_date,
    )
    logger.info("expense_updated_endpoint", expense_id=str(expense_id), user_id=str(current_user.id))
    return ExpenseResponse.model_validate(expense)


@router.delete(
    "/families/{family_id}/expenses/{expense_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_expense(
    family_id: uuid.UUID,
    expense_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> dict[str, str]:
    """Delete an expense."""
    current_user, _ = membership

    # Fetch the expense to know its month, then enforce grace period
    existing = await expense_service.get_expense(uow, family_id=family_id, expense_id=expense_id)
    if not await _is_editable(uow, family_id, existing.year_month):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Grace period expired. Past-month expenses are read-only.",
        )

    await expense_service.delete_expense(uow, family_id=family_id, expense_id=expense_id)
    logger.info("expense_deleted_endpoint", expense_id=str(expense_id), user_id=str(current_user.id))
    return {"message": "Expense deleted"}


@router.get(
    "/families/{family_id}/budget/summary",
    response_model=BudgetSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_budget_summary(
    family_id: uuid.UUID,
    month: str = Query(..., description="Month in YYYY-MM format"),
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
) -> BudgetSummaryResponse:
    """Get budget summary for a family for the given month."""
    is_editable = await _is_editable(uow, family_id, month)
    return await expense_service.get_budget_summary(uow, family_id=family_id, year_month=month, is_editable=is_editable)
