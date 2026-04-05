"""Monthly goals router: CRUD endpoints for family monthly budget goals."""

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_family_admin, require_family_member
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.user import User
from app.schemas.monthly_goal import (
    BulkGoalsRequest,
    BulkGoalsResponse,
    GoalsListResponse,
    MonthlyGoalResponse,
    MonthlyGoalUpdate,
)
from app.services import monthly_goal_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["monthly_goals"])

_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _validate_year_month(value: str) -> None:
    """Raise HTTP 422 if value is not in YYYY-MM format."""
    if not _YEAR_MONTH_RE.match(value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month must be in YYYY-MM format",
        )


@router.get(
    "/families/{family_id}/goals",
    response_model=GoalsListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_goals(
    family_id: uuid.UUID,
    month: str = Query(..., description="Filter by month in YYYY-MM format"),
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    db: AsyncSession = Depends(get_db),
) -> GoalsListResponse:
    """List goals for a family for the given month (any member)."""
    _validate_year_month(month)
    goals, has_previous_goals = await monthly_goal_service.list_goals(db, family_id=family_id, year_month=month)
    return GoalsListResponse(
        year_month=month,
        goals=[MonthlyGoalResponse.model_validate(g) for g in goals],
        has_previous_goals=has_previous_goals,
    )


@router.put(
    "/families/{family_id}/goals",
    response_model=BulkGoalsResponse,
    status_code=status.HTTP_200_OK,
)
async def bulk_upsert_goals(
    family_id: uuid.UUID,
    body: BulkGoalsRequest,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> BulkGoalsResponse:
    """Bulk upsert goals for a family month (admin only, all-or-nothing)."""
    current_user, _ = membership
    goals_list = [{"category_id": g.category_id, "amount_cents": g.amount_cents} for g in body.goals]
    counts = await monthly_goal_service.bulk_upsert_goals(
        db,
        family_id=family_id,
        year_month=body.year_month,
        goals_list=goals_list,
    )
    # Re-fetch the resulting goals to return them in the response
    updated_goals, _ = await monthly_goal_service.list_goals(db, family_id=family_id, year_month=body.year_month)
    logger.info(
        "bulk_upsert_goals_endpoint",
        family_id=str(family_id),
        year_month=body.year_month,
        user_id=str(current_user.id),
        **counts,
    )
    return BulkGoalsResponse(
        year_month=body.year_month,
        created=counts["created"],
        updated=counts["updated"],
        deleted=counts["deleted"],
        goals=[MonthlyGoalResponse.model_validate(g) for g in updated_goals],
    )


@router.put(
    "/families/{family_id}/goals/{goal_id}",
    response_model=MonthlyGoalResponse,
    status_code=status.HTTP_200_OK,
)
async def update_goal(
    family_id: uuid.UUID,
    goal_id: uuid.UUID,
    body: MonthlyGoalUpdate,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> MonthlyGoalResponse:
    """Update a single goal with optimistic locking (admin only)."""
    current_user, _ = membership
    goal = await monthly_goal_service.update_goal(
        db,
        goal_id=goal_id,
        family_id=family_id,
        amount_cents=body.amount_cents,
        expected_version=body.expected_version,
    )
    logger.info("goal_updated_endpoint", goal_id=str(goal_id), user_id=str(current_user.id))
    return MonthlyGoalResponse.model_validate(goal)


@router.delete(
    "/families/{family_id}/goals/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_goal(
    family_id: uuid.UUID,
    goal_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a goal (admin only). Returns 204 No Content."""
    current_user, _ = membership
    await monthly_goal_service.delete_goal(db, goal_id=goal_id, family_id=family_id)
    logger.info("goal_deleted_endpoint", goal_id=str(goal_id), user_id=str(current_user.id))
