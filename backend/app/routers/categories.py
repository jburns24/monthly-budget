"""Categories router: CRUD endpoints for family budget categories."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_family_admin, require_family_member
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryDeleteResponse, CategoryResponse, CategoryUpdate, SeedResponse
from app.services import category_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["categories"])


@router.get(
    "/families/{family_id}/categories",
    response_model=list[CategoryResponse],
    status_code=status.HTTP_200_OK,
)
async def list_categories(
    family_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    db: AsyncSession = Depends(get_db),
) -> list[CategoryResponse]:
    """List all active categories for a family (any member)."""
    categories = await category_service.list_active_categories(db, family_id)
    return [CategoryResponse.model_validate(c) for c in categories]


@router.post(
    "/families/{family_id}/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_category(
    family_id: uuid.UUID,
    body: CategoryCreate,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    """Create a new category for a family (admin only)."""
    current_user, _ = membership
    category = await category_service.create_category(
        db,
        family_id=family_id,
        name=body.name,
        icon=body.icon,
        sort_order=body.sort_order,
    )
    logger.info("category_created_endpoint", category_id=str(category.id), user_id=str(current_user.id))
    return CategoryResponse.model_validate(category)


@router.put(
    "/families/{family_id}/categories/{category_id}",
    response_model=CategoryResponse,
    status_code=status.HTTP_200_OK,
)
async def update_category(
    family_id: uuid.UUID,
    category_id: uuid.UUID,
    body: CategoryUpdate,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> CategoryResponse:
    """Update a category's fields (admin only)."""
    current_user, _ = membership
    category = await category_service.update_category(
        db,
        family_id=family_id,
        category_id=category_id,
        name=body.name,
        icon=body.icon,
        sort_order=body.sort_order,
    )
    logger.info("category_updated_endpoint", category_id=str(category_id), user_id=str(current_user.id))
    return CategoryResponse.model_validate(category)


@router.delete(
    "/families/{family_id}/categories/{category_id}",
    response_model=CategoryDeleteResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_category(
    family_id: uuid.UUID,
    category_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> CategoryDeleteResponse:
    """Delete or archive a category (admin only)."""
    current_user, _ = membership
    result = await category_service.delete_category(db, family_id=family_id, category_id=category_id)
    logger.info("category_deleted_endpoint", category_id=str(category_id), user_id=str(current_user.id))
    return CategoryDeleteResponse(
        message="Category deleted" if result.get("deleted") else "Category archived",
        deleted=result.get("deleted", False),
        archived=result.get("archived", False),
        expense_count=result.get("expense_count", 0),
    )


@router.post(
    "/families/{family_id}/categories/seed",
    response_model=SeedResponse,
    status_code=status.HTTP_200_OK,
)
async def seed_categories(
    family_id: uuid.UUID,
    membership: tuple[User, FamilyMember] = Depends(require_family_admin),
    db: AsyncSession = Depends(get_db),
) -> SeedResponse:
    """Seed default categories for a family (admin only, idempotent)."""
    current_user, _ = membership
    created_count = await category_service.seed_default_categories(db, family_id=family_id)
    logger.info("categories_seeded_endpoint", family_id=str(family_id), user_id=str(current_user.id))
    return SeedResponse(
        message=f"Seeded {created_count} default categories",
        created_count=created_count,
    )
