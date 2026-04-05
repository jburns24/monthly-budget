# 04-spec-categories-management

## Introduction/Overview

This epic implements family-scoped spending categories with full CRUD operations, soft-delete/archive semantics, and admin-only write access for the Monthly Budget application. Categories are the organizational backbone for all downstream spending features — expenses (Epic 5), monthly goals (Epic 6), and receipt scanning (Epic 7) all depend on categories existing.

The primary goal is: a family admin can create, rename, reorder, and archive spending categories; all family members can view active categories; and archived categories remain visible on historical expense records while being hidden from new entry forms.

## Goals

- Create the `categories` database table with Alembic migration (reversible), matching the PRD schema exactly (UUID PK, family_id FK, name, icon, sort_order, is_active, created_at, UNIQUE(family_id, name))
- Implement four CRUD API endpoints (`GET`, `POST`, `PUT`, `DELETE`) under `/api/families/{family_id}/categories` with RBAC enforcement (member reads, admin writes)
- Implement a seed endpoint (`POST /api/families/{family_id}/categories/seed`) that bulk-creates the 6 PRD-suggested default categories (Groceries, Dining, Transport, Entertainment, Bills, Other)
- Build a Categories management page on the frontend with list view, create/edit dialogs, archive confirmation, and role-based conditional rendering
- Enable the existing disabled "Categories" tab in BottomNavigation and wire up the `/categories` route
- Achieve full test coverage: model unit tests, service tests, API endpoint tests, integration tests (backend), component tests (frontend), and E2E Playwright tests

## User Stories

- **As a family admin**, I want to create spending categories so that family members can classify their expenses.
- **As a family admin**, I want to rename or change the icon of a category so that it better reflects our spending patterns.
- **As a family admin**, I want to reorder categories so that the most-used ones appear first in dropdowns.
- **As a family admin**, I want to delete a category so that it no longer clutters the category list. If expenses reference it, I understand it will be archived instead.
- **As a family admin**, I want to seed default categories when setting up our budget so that we don't start from a blank slate.
- **As a family member**, I want to view all active categories so that I know which categories are available when logging expenses.
- **As a developer**, I want the categories model and API to be complete and tested so that Epics 5, 6, and 7 can depend on it without blockers.

## Demoable Units of Work

### Unit 1: Database — Categories Table, Model & Migration

**Purpose:** Create the foundational database table and SQLAlchemy ORM model for categories, establishing the schema that all subsequent units depend on.

**Functional Requirements:**
- The system shall create a `categories` table with columns: `id` (UUID PK, default gen_random_uuid()), `family_id` (UUID FK to families ON DELETE CASCADE, NOT NULL), `name` (VARCHAR(100) NOT NULL), `icon` (VARCHAR(50), nullable — stores emoji characters), `sort_order` (INTEGER NOT NULL DEFAULT 0), `is_active` (BOOLEAN NOT NULL DEFAULT true), `created_at` (TIMESTAMPTZ NOT NULL DEFAULT now())
- The system shall enforce a UNIQUE constraint on `(family_id, name)` to prevent duplicate category names within a family
- The system shall create an index `idx_categories_family` on `categories(family_id)` for fast family-scoped queries
- The system shall provide the migration via Alembic with both `upgrade` and `downgrade` paths
- The system shall create a SQLAlchemy async ORM model `Category` in `backend/app/models/category.py` using `Mapped[]` type annotations, matching the existing model patterns (UUID as_uuid, TIMESTAMP with timezone, ForeignKey with ondelete, `__table_args__` tuple)
- The system shall register the Category model in `backend/app/models/__init__.py` so Alembic autogenerate detects it
- The system shall add a `categories` relationship on the `Family` model with `back_populates="family"` and `cascade="all, delete-orphan"`
- The system shall add the `categories` table to the `test_reset` endpoint's truncation order in `backend/app/routers/dev_auth.py` (before families, as categories have FK to families)

**Proof Artifacts:**
- CLI: `cd backend && uv run alembic upgrade head` succeeds and `uv run alembic downgrade -1` succeeds, demonstrating reversible migration
- Test: Model unit tests in `backend/tests/test_categories_models.py` pass, demonstrating: Category can be created and retrieved with all fields; UNIQUE(family_id, name) constraint raises IntegrityError on duplicate; is_active defaults to true; sort_order defaults to 0; CASCADE delete removes categories when family is deleted

### Unit 2: Service Layer — Category CRUD Business Logic

**Purpose:** Implement the category service with all business logic including create, list, update, delete/archive, and seed operations.

**Functional Requirements:**
- The system shall implement `create_category(db, family_id, name, icon, sort_order)` that creates a category and returns the ORM object, raising HTTPException(409) if a category with the same name already exists in the family
- The system shall implement `list_active_categories(db, family_id)` that returns all categories where `is_active=true` for the given family, ordered by `sort_order ASC, name ASC`
- The system shall implement `update_category(db, family_id, category_id, name, icon, sort_order)` that updates the specified fields (only non-None values), raising HTTPException(404) if the category doesn't exist or doesn't belong to the family, and HTTPException(409) if the new name conflicts with an existing category in the same family
- The system shall implement `delete_category(db, family_id, category_id)` that:
  - If no expenses reference the category: hard-deletes the row and returns `{"deleted": true}`
  - If expenses reference the category: sets `is_active=false` (archives) and returns `{"deleted": false, "archived": true, "expense_count": N}` with the CATEGORY_HAS_EXPENSES error pattern
  - Raises HTTPException(404) if the category doesn't exist or doesn't belong to the family
- The system shall implement `seed_default_categories(db, family_id)` that bulk-creates the 6 default categories (Groceries, Dining, Transport, Entertainment, Bills, Other) with appropriate emoji icons and sequential sort_order, skipping any that already exist (idempotent)
- All service functions shall use `await db.flush()` (not commit) and log operations with `structlog.get_logger(__name__)`

**Proof Artifacts:**
- Test: Service unit tests in `backend/tests/test_categories_service.py` pass, covering: successful create; duplicate name 409; list returns only active sorted correctly; update partial fields; update name conflict 409; delete hard-deletes when no expenses; delete archives when expenses exist; seed creates defaults; seed is idempotent

### Unit 3: API Endpoints — REST Routes with RBAC & Pydantic Schemas

**Purpose:** Expose category operations as REST API endpoints with proper authentication, authorization, request validation, and response serialization.

**Functional Requirements:**
- The system shall create Pydantic schemas in `backend/app/schemas/category.py`:
  - `CategoryCreate(BaseModel)`: name (str, Field(min_length=1, max_length=100)), icon (str | None = None), sort_order (int = 0)
  - `CategoryUpdate(BaseModel)`: name (str | None = None, Field(min_length=1, max_length=100) when provided), icon (str | None = None), sort_order (int | None = None)
  - `CategoryResponse(BaseModel)`: id (UUID), family_id (UUID), name (str), icon (str | None), sort_order (int), is_active (bool), created_at (datetime)
  - `CategoryDeleteResponse(BaseModel)`: message (str), deleted (bool), archived (bool = False), expense_count (int = 0)
  - `SeedResponse(BaseModel)`: message (str), created_count (int)
- The system shall create a router in `backend/app/routers/categories.py` with `APIRouter(prefix="/api", tags=["categories"])`:
  - `GET /families/{family_id}/categories` — `Depends(require_family_member)` — returns `list[CategoryResponse]`
  - `POST /families/{family_id}/categories` — `Depends(require_family_admin)` — returns `CategoryResponse` with status 201
  - `PUT /families/{family_id}/categories/{category_id}` — `Depends(require_family_admin)` — returns `CategoryResponse`
  - `DELETE /families/{family_id}/categories/{category_id}` — `Depends(require_family_admin)` — returns `CategoryDeleteResponse`
  - `POST /families/{family_id}/categories/seed` — `Depends(require_family_admin)` — returns `SeedResponse`
- The system shall register the categories router in `backend/app/main.py`
- The system shall add a `create_test_category(db, family, **overrides)` factory function in `backend/tests/conftest.py`

**Proof Artifacts:**
- Test: API endpoint tests in `backend/tests/test_categories_api.py` pass, covering: GET returns active categories for member; POST creates category for admin; POST returns 403 for non-admin; PUT updates fields for admin; DELETE hard-deletes for admin; DELETE archives when expenses exist; seed creates defaults; non-member gets 404 (privacy)
- Test: Integration tests in `backend/tests/test_categories_integration.py` pass, covering: full category lifecycle (create, list, update, archive); seed then CRUD; RBAC enforcement across admin/member/non-member

### Unit 4: Frontend — Categories Page, Components & Navigation

**Purpose:** Build the user-facing categories management interface with list view, create/edit dialogs, archive confirmation, and role-based access control.

**Functional Requirements:**
- The system shall create TypeScript types in `frontend/src/types/categories.ts`: `Category` (matching CategoryResponse), `CategoryCreate`, `CategoryUpdate`
- The system shall create API client functions in `frontend/src/api/categories.ts`: `getCategories(familyId)`, `createCategory(familyId, data)`, `updateCategory(familyId, categoryId, data)`, `deleteCategory(familyId, categoryId)`, `seedCategories(familyId)` — all using `apiClient()` with the established error-handling pattern
- The system shall create a `CategoriesPage` component in `frontend/src/pages/CategoriesPage.tsx` that:
  - Uses `useFamilyContext()` for familyId and role
  - Shows a loading spinner while fetching
  - Shows an error message on fetch failure
  - Renders the category list when data is available
  - Shows a "Seed defaults" button when the category list is empty and user is admin
- The system shall create a `CategoryList` component that:
  - Displays each category as a card/row with emoji icon, name, and sort order
  - Shows edit and delete buttons only when `role === 'admin'` (via `useFamilyContext()`)
  - Uses the `brand` color palette for the primary layout consistent with existing pages
- The system shall create a `CreateCategoryDialog` component that:
  - Opens from an "Add Category" button (admin-only, hidden for members)
  - Contains a form with: name input (required, max 100 chars), icon input (optional emoji picker or text input), sort order input (optional, defaults to 0)
  - Uses `useMutation` with `onSuccess` → `toaster.create({ type: 'success' })` + `queryClient.invalidateQueries({ queryKey: ['categories', familyId] })` and `onError` → `toaster.create({ type: 'error' })`
  - Follows the Chakra UI v3 `DialogRoot` pattern from existing dialogs
- The system shall create an `EditCategoryDialog` component following the same mutation/dialog pattern as Create, pre-populating fields from the selected category
- The system shall create an `ArchiveCategoryDialog` component that shows a confirmation dialog with the category name, uses DELETE mutation, and displays appropriate messaging based on whether the category was hard-deleted or archived
- The system shall enable the "Categories" tab in `BottomNavigation.tsx` by removing the `disabled` prop on line 164
- The system shall add a `/categories` route in `App.tsx` wrapped in `ProtectedRoute` and `ProtectedLayout`, matching the existing pattern for `/family`
- The system shall use React Query with `queryKey: ['categories', familyId]` and `enabled: familyId !== null`

**Proof Artifacts:**
- Test: Component tests in `frontend/src/__tests__/CategoriesPage.test.tsx` pass, covering: loading state renders spinner; categories render in list; admin sees add/edit/delete buttons; member does not see add/edit/delete buttons; create dialog opens and submits; empty state shows seed button for admin
- URL: `/categories` page renders category list when logged in as a family member
- URL: Admin user can create, edit, and archive a category through the UI

### Unit 5: E2E Tests — Full Category Lifecycle via Playwright

**Purpose:** Validate the complete categories feature end-to-end in a real browser, exercising the full stack from UI through API to database.

**Functional Requirements:**
- The system shall create a `CategoriesPage` page object in `e2e/pages/categories.page.ts` with locators for: add button, category name input, icon input, submit button, category list items, edit buttons, delete buttons, seed button, and confirmation dialogs
- The system shall create E2E tests in `e2e/tests/categories.spec.ts` that:
  - Reset test data and authenticate via dev-login in `beforeEach`
  - Create a family via API before testing categories (categories require a family)
  - Test: admin creates a category and sees it in the list
  - Test: admin edits a category name and sees the updated name
  - Test: admin deletes a category (no expenses) and it disappears from the list
  - Test: seed defaults creates 6 categories
  - Test: member can view categories but cannot see admin actions
- The system shall add a `createCategoryViaApi(ctx, familyId, name, icon?)` helper to `e2e/fixtures/test-data.ts`
- All E2E tests shall follow the existing patterns: `resetTestData()`, `storageState` for auth, `page.waitForResponse()` for API verification, Page Object Model for locator management

**Proof Artifacts:**
- Test: `npx playwright test e2e/tests/categories.spec.ts` passes all tests
- Screenshot: Categories page showing list of categories with admin controls visible

## Non-Goals (Out of Scope)

- **Monthly goals** (Epic 6) — goal setting, progress bars, and rollover logic are a separate epic that depends on categories
- **Expense entry form** (Epic 5) — the category dropdown in expense forms is part of Epic 5
- **Onboarding flow** — the full onboarding wizard that calls seed is a separate epic; we only provide the seed API
- **Category hierarchy/subcategories** — the PRD explicitly specifies flat categories
- **Row-Level Security (RLS) policies** — per the epic breakdown decision, security hardening is a separate epic; RBAC is enforced at the application layer via FastAPI dependencies
- **Drag-and-drop reordering** — sort_order is managed via the edit form for MVP; drag-and-drop UX is a polish item
- **Category color field** — the PRD schema uses `icon` (emoji), not a separate color field; UI styling uses the existing brand/accent palette
- **Audit logging** — audit_log table doesn't exist yet; deferred to security hardening epic
- **pg_trgm extension/index** — trigram-based category suggestion is part of receipt scanning (Epic 7)

## Design Considerations

- **Mobile-first layout**: Categories page should follow the same Container/Card pattern as FamilyPage. Category items displayed as a vertical list with icon, name, and admin action buttons
- **Empty state**: When no categories exist, show a helpful empty state with "Seed default categories" CTA for admins, and "No categories yet" message for members
- **Icon input**: Simple text input where users paste an emoji character. No full emoji picker for MVP — keep it lightweight
- **Responsive**: The page renders within the existing `pb="64px"` padding for the fixed BottomNavigation
- **Toast feedback**: Use existing `toaster.create()` pattern for success/error messages on all mutations
- **Color system**: Use existing `brand`, `accent`, and `teal` color tokens from `theme.ts`

## Repository Standards

- **Python**: ruff (lint+format, line-length=120, py312), mypy (--ignore-missing-imports), structlog logging
- **TypeScript**: ESLint, Prettier, tsc --noEmit (strict mode)
- **Package manager**: uv for Python, npm for JavaScript
- **All backend code is async**: async routes, async SQLAlchemy, async tests with pytest-asyncio (asyncio_mode="auto")
- **Services use `db.flush()`** (not commit) — `get_db()` dependency handles transaction lifecycle
- **ORM models**: `Mapped[]` types, UUID PKs, `__table_args__` with constraints and indexes
- **Pydantic schemas**: Separate Create/Update/Response classes inheriting BaseModel
- **Frontend forms**: `useState` + `useMutation` + `toaster.create()` + `queryClient.invalidateQueries()`
- **Testing**: Factory functions in conftest.py, NullPool sessions in API test files, `app.dependency_overrides[get_db]`, `authenticated_client` factory fixture
- **Pre-commit hooks** are the single source of truth for all quality checks

## Technical Considerations

- **Migration dependency chain**: New migration depends on `f3a9c2d1e4b7` (family management tables). The categories table has FK to families which already exists.
- **Future expense FK**: The PRD specifies `expenses.category_id REFERENCES categories(id) ON DELETE RESTRICT`. This will be added in Epic 5's migration, not here. However, the delete_category service should already check for expense references (using a query, not FK constraint) to implement the archive-if-referenced behavior. For now, since no expenses table exists, delete will always hard-delete. The service should be structured so that adding the expense check is a simple addition.
- **Seed idempotency**: The seed endpoint must be idempotent — calling it twice should not create duplicates. It should skip categories whose names already exist in the family.
- **Query performance**: With the `idx_categories_family` index, family-scoped queries will be efficient. Typical families will have 5-20 categories, so no pagination is needed.
- **Sort order management**: sort_order is an integer field. When a new category is created without specifying sort_order, it defaults to 0. The frontend can manage ordering by sending updated sort_order values via PUT.

## Security Considerations

- **RBAC enforcement**: All write operations (POST, PUT, DELETE, seed) require `require_family_admin` dependency. Read operations require `require_family_member`.
- **Privacy-preserving errors**: Non-members attempting to access a family's categories receive 404 "Family not found" (not 403), consistent with existing family endpoint behavior.
- **Input validation**: Category name is validated via Pydantic (min_length=1, max_length=100). Icon field is nullable VARCHAR(50) — no special validation beyond length.
- **No data leakage**: Category list only returns categories for the authenticated user's family. There is no endpoint to list categories across families.

## Success Metrics

- All backend tests pass (model, service, API, integration) with >90% line coverage on new code
- All frontend component tests pass
- All E2E Playwright tests pass
- Categories tab is active in BottomNavigation and navigates to a functional page
- Admin can complete full CRUD lifecycle: seed defaults, create custom, edit, delete/archive
- Member can view categories but cannot modify them
- Pre-commit hooks pass on all new/modified files

## Open Questions

- No open questions at this time. All clarifying questions were resolved in Round 1.
