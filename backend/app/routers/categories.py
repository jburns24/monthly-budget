"""Categories router: CRUD endpoints for family budget categories."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI

from app.dependencies import get_llm_client, require_family_admin, require_family_member
from app.deps.provider import get_uow
from app.logging import get_logger
from app.models.family_member import FamilyMember
from app.models.user import User
from app.ports.unit_of_work import UnitOfWork
from app.schemas.category import (
    CategoryCreate,
    CategoryDeleteResponse,
    CategoryResponse,
    CategorySuggestRequest,
    CategorySuggestResponse,
    CategoryUpdate,
    SeedResponse,
)
from app.services import category_classifier, category_service, rate_limiter

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
    uow: UnitOfWork = Depends(get_uow),
) -> list[CategoryResponse]:
    """List all active categories for a family (any member)."""
    categories = await category_service.list_active_categories(uow, family_id)
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
    uow: UnitOfWork = Depends(get_uow),
) -> CategoryResponse:
    """Create a new category for a family (admin only)."""
    current_user, _ = membership
    category = await category_service.create_category(
        uow,
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
    uow: UnitOfWork = Depends(get_uow),
) -> CategoryResponse:
    """Update a category's fields (admin only)."""
    current_user, _ = membership
    category = await category_service.update_category(
        uow,
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
    uow: UnitOfWork = Depends(get_uow),
) -> CategoryDeleteResponse:
    """Delete or archive a category (admin only)."""
    current_user, _ = membership
    result = await category_service.delete_category(uow, family_id=family_id, category_id=category_id)
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
    uow: UnitOfWork = Depends(get_uow),
) -> SeedResponse:
    """Seed default categories for a family (admin only, idempotent)."""
    current_user, _ = membership
    created_count = await category_service.seed_default_categories(uow, family_id=family_id)
    logger.info("categories_seeded_endpoint", family_id=str(family_id), user_id=str(current_user.id))
    return SeedResponse(
        message=f"Seeded {created_count} default categories",
        created_count=created_count,
    )


async def _check_suggest_rate_limit(family_id: uuid.UUID) -> None:
    allowed, _ = await rate_limiter.check_and_increment_category_suggest(family_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily category suggestion limit reached. Try again tomorrow.",
            headers={"Retry-After": "86400"},
        )


@router.post(
    "/families/{family_id}/categories/suggest",
    response_model=CategorySuggestResponse,
    status_code=status.HTTP_200_OK,
)
async def suggest_category(
    family_id: uuid.UUID,
    body: CategorySuggestRequest,
    membership: tuple[User, FamilyMember] = Depends(require_family_member),
    uow: UnitOfWork = Depends(get_uow),
    llm: AsyncOpenAI = Depends(get_llm_client),
    _rate_limit: None = Depends(_check_suggest_rate_limit),
) -> CategorySuggestResponse:
    """Suggest an active category for an expense description (any member).

    Always 200: "no suggestion" is a normal answer (both fields null), including
    when the decision model is slow, unsure, or unavailable.
    """
    category = await category_classifier.suggest_category(llm, uow.categories, family_id, body.description)
    if category is None:
        return CategorySuggestResponse()
    return CategorySuggestResponse(category_id=category.id, category_name=category.name)
