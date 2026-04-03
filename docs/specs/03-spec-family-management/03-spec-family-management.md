# 03-spec-family-management

## Introduction/Overview

This epic implements family (household) management with role-based access control (RBAC) for the Monthly Budget application. It creates the `families`, `family_members`, and `invites` database tables, a service layer with RBAC enforcement, backend API endpoints for family CRUD and invite management, and frontend pages for viewing/managing family members and roles — establishing the multi-user collaboration layer that all subsequent data-scoped epics depend on.

The primary goal is: a user can create a family, invite other registered users by email, accept/decline invites, and manage member roles (admin/member), with all family-scoped operations gated by RBAC permissions.

## Goals

- Create `families`, `family_members`, and `invites` tables with Alembic migration (reversible)
- Enforce the one-family-per-user constraint at the application layer
- Implement RBAC permission checking as reusable FastAPI dependencies (`require_family_member`, `require_family_admin`)
- Build family CRUD endpoints: create family, get family details + members
- Build invite endpoints: send invite (privacy-preserving), list pending invites, accept/decline
- Build member management endpoints: remove member, change role, leave family
- Add a `/family` bottom navigation tab with member list, invite UI, and role management
- Establish a `FamilyContext` on the frontend so downstream epics can scope data by family

## User Stories

- **As a new user**, I want to create a family (household) so that I can start tracking shared expenses.
- **As a family admin**, I want to invite another registered user by email so that they can join my household's budget.
- **As an invited user**, I want to see pending invitations and accept or decline them so that I control which family I join.
- **As a family admin**, I want to change a member's role (admin/member) so that I can delegate management responsibilities.
- **As a family admin**, I want to remove a member so that they no longer have access to family data.
- **As a family member**, I want to leave a family so that I can join a different household.
- **As a developer**, I want reusable RBAC dependencies so that all future endpoints can easily require family membership or admin role.

## Demoable Units of Work

### Unit 1: Database — Families, Members & Invites

**Purpose:** Create the foundational database tables for family management and the join/invite system.

**Functional Requirements:**
- The system shall create a `families` table with columns: `id` (UUID PK), `name` (VARCHAR(255) NOT NULL), `timezone` (VARCHAR(64) NOT NULL DEFAULT 'America/New_York'), `edit_grace_days` (INTEGER NOT NULL DEFAULT 7), `created_by` (UUID FK to users ON DELETE RESTRICT), `created_at` (TIMESTAMPTZ NOT NULL DEFAULT now())
- The system shall create a `family_members` table with columns: `id` (UUID PK), `family_id` (UUID FK to families ON DELETE CASCADE), `user_id` (UUID FK to users ON DELETE CASCADE), `role` (VARCHAR(20) NOT NULL DEFAULT 'member' CHECK IN ('admin', 'member')), `joined_at` (TIMESTAMPTZ NOT NULL DEFAULT now()), with UNIQUE constraint on (family_id, user_id)
- The system shall create an `invites` table with columns: `id` (UUID PK), `family_id` (UUID FK to families ON DELETE CASCADE), `invited_user_id` (UUID FK to users ON DELETE CASCADE), `invited_by` (UUID FK to users ON DELETE CASCADE), `status` (VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK IN ('pending', 'accepted', 'declined')), `created_at` (TIMESTAMPTZ NOT NULL DEFAULT now()), `responded_at` (TIMESTAMPTZ nullable), with UNIQUE constraint on (family_id, invited_user_id, status)
- The system shall create indexes: `idx_family_members_family` on family_members(family_id), `idx_family_members_user` on family_members(user_id), `idx_invites_invited_user` on invites(invited_user_id, status)
- The system shall provide the migration via Alembic with both `upgrade` and `downgrade` paths
- The system shall create SQLAlchemy async ORM models for `Family`, `FamilyMember`, and `Invite` with appropriate relationships

**Proof Artifacts:**
- CLI: `alembic upgrade head` succeeds and `alembic downgrade -1` succeeds, demonstrating reversible migration
- Test: Model unit tests pass, demonstrating ORM models map correctly to the schema and constraints (unique, check) are enforced

### Unit 2: Service Layer & RBAC Dependencies

**Purpose:** Implement the family service layer with business logic and reusable RBAC FastAPI dependencies that gate all family-scoped endpoints.

**Functional Requirements:**
- The system shall provide a `FamilyService` class (or module) with async methods: `create_family`, `get_family_with_members`, `invite_user`, `respond_to_invite`, `remove_member`, `change_role`, `leave_family`
- The `create_family` method shall: verify the user is not already in a family (raise 409 if they are), create the family record, add the creator as an `admin` member, return the family
- The `invite_user` method shall: look up the target user by email. If the user does not exist OR is already in a family OR already has a pending invite to this family, the method shall silently succeed (return a generic success) without revealing whether the email matches a registered user. If the user exists and is eligible, create a pending invite record.
- The `respond_to_invite` method shall: validate the invite belongs to the current user and is pending, update status to 'accepted' or 'declined', if accepted add the user as a 'member' to the family (enforcing one-family constraint — reject if already in a family), set `responded_at`
- The `remove_member` method shall: prevent removing the family owner (created_by), prevent removing the last admin, remove the family_members record
- The `change_role` method shall: prevent demoting the family owner, prevent demoting the last admin, update the role
- The `leave_family` method shall: prevent the owner from leaving, remove the member record
- The system shall provide a FastAPI dependency `require_family_member(family_id)` that extracts the current user (via `get_current_user`), verifies they are a member of the specified family, and returns a tuple of (User, FamilyMember)
- The system shall provide a FastAPI dependency `require_family_admin(family_id)` that extends `require_family_member` and additionally verifies the member has role='admin'
- The system shall return HTTP 403 for RBAC violations and HTTP 404 for family-not-found (do not distinguish between "family doesn't exist" and "you don't have access")

**Proof Artifacts:**
- Test: `create_family` creates family + admin membership, returns family
- Test: `create_family` for user already in a family returns 409
- Test: `invite_user` with non-existent email returns success (privacy-preserving)
- Test: `invite_user` with valid email creates pending invite
- Test: `respond_to_invite` accept adds member to family
- Test: `respond_to_invite` accept when already in a family returns 409
- Test: `remove_member` on owner is blocked (403)
- Test: `change_role` demoting last admin is blocked (403)
- Test: `leave_family` for owner is blocked (403)
- Test: `require_family_member` returns 403 for non-member
- Test: `require_family_admin` returns 403 for member (non-admin)

### Unit 3: Family API Endpoints

**Purpose:** Expose the family management REST API endpoints using the service layer and RBAC dependencies.

**Functional Requirements:**
- The system shall expose `POST /api/families` (JWT-protected) accepting `{ "name": "...", "timezone": "..." }` — creates family with current user as admin, returns family details (201)
- The system shall expose `GET /api/families/{family_id}` (require_family_member) — returns family details including member list with roles (200)
- The system shall expose `POST /api/families/{family_id}/invites` (require_family_admin) accepting `{ "email": "..." }` — creates invite, always returns generic success message `{ "message": "If a user with that email exists, they will receive an invitation." }` (200)
- The system shall expose `GET /api/invites` (JWT-protected) — returns pending invites for the current user (200)
- The system shall expose `POST /api/invites/{invite_id}/respond` (JWT-protected) accepting `{ "action": "accept" | "decline" }` — processes invite response (200)
- The system shall expose `DELETE /api/families/{family_id}/members/{user_id}` (require_family_admin) — removes member (200)
- The system shall expose `PATCH /api/families/{family_id}/members/{user_id}` (require_family_admin) accepting `{ "role": "admin" | "member" }` — changes role (200)
- The system shall expose `POST /api/families/{family_id}/leave` (require_family_member) — current user leaves family (200)
- The system shall add Pydantic request/response schemas in `app/schemas/family.py` for all endpoints
- The system shall update `GET /api/me` to include `family` field (null or `{ id, name, role }`) in the response

**Proof Artifacts:**
- Test: POST `/api/families` creates family and returns 201 with family details
- Test: GET `/api/families/{id}` returns member list for a family member, 403 for non-member
- Test: POST invite endpoint always returns same success message regardless of email validity
- Test: GET `/api/invites` returns only pending invites for current user
- Test: Accept invite adds user to family, decline updates status
- Test: DELETE member endpoint removes member, 403 for non-admin
- Test: PATCH role endpoint changes role, blocks last-admin demotion
- Test: `/api/me` includes family info when user belongs to a family

### Unit 4: Frontend — Family Pages & Navigation

**Purpose:** Build the family management UI with bottom navigation tab, member list, invite flow, and role management.

**Functional Requirements:**
- The system shall add a bottom navigation bar component with tabs: Home, Categories (placeholder), Family, Settings (placeholder) — matching the PRD wireframe
- The system shall add a `/family` route rendered inside `ProtectedRoute`
- The system shall render a "Create Family" page when the user has no family (name input + timezone selector + create button)
- The system shall render a "Family Dashboard" page when the user belongs to a family, showing: family name, member list (avatar, name, role badge), and an invite section (for admins)
- The system shall show a pending invites banner/section on the home page or family page when the user has pending invites, with accept/decline buttons
- The system shall provide an "Invite Member" form (admin-only) with an email input and send button. On submit, show the generic success toast regardless of response.
- The system shall provide role management for admins: a dropdown or toggle on each member to change their role (admin/member), with confirmation dialog
- The system shall provide a "Remove Member" button for admins (with confirmation dialog) and a "Leave Family" button for non-owner members
- The system shall create a `FamilyContext` (React Context) that provides the current user's family ID and role to all child components, populated from the `/api/me` response
- The system shall use React Query for all family data fetching with appropriate cache invalidation on mutations
- The system shall use Chakra UI components consistent with the existing theme

**Proof Artifacts:**
- Screenshot: `/family` page with no family shows "Create Family" form
- Screenshot: `/family` page with family shows member list and invite section
- Test: Bottom navigation renders with correct tabs and active states
- Test: Create family form submits and redirects to family dashboard
- Test: Invite form shows generic success message on submit
- Test: FamilyContext provides family ID and role to child components

### Unit 5: Integration Tests & Edge Cases

**Purpose:** Verify end-to-end flows and edge cases across the full stack.

**Functional Requirements:**
- The system shall include a backend integration test exercising the full flow: create family → invite user → accept invite → verify member list → change role → remove member
- The system shall include a backend test for the privacy-preserving invite: invite non-existent email returns same response as valid email
- The system shall include a backend test for the one-family constraint: user in family A tries to create family B → 409, user in family A accepts invite to family B → 409
- The system shall include a backend test for owner protection: owner cannot leave, owner cannot be removed, owner cannot be demoted
- The system shall include a backend test for last-admin protection: single admin cannot be demoted
- The system shall include a frontend integration test (Vitest + RTL) that verifies the family creation and member display flow with mocked API responses
- The system shall include test utilities: `create_test_family` factory (creates family + admin member), `create_test_invite` factory — added to `conftest.py`

**Proof Artifacts:**
- Test: Full family lifecycle integration test passes end-to-end
- Test: Privacy-preserving invite test passes
- Test: One-family constraint tests pass
- Test: Owner/admin protection tests pass
- CLI: `task test` passes with all family management tests green

## Non-Goals (Out of Scope)

1. **Row-Level Security (RLS)** — deferred to the security hardening epic per the agreed approach. Access control is enforced at the application layer via RBAC dependencies.
2. **Categories management** — belongs to Epic 04. The `/categories` nav tab will be a placeholder.
3. **Expense scoping by family** — belongs to Epic 05. This epic establishes the family context but does not scope expenses.
4. **Email/push notifications for invites** — not in PRD MVP scope. Invites are visible in-app only.
5. **Family deletion** — not in PRD MVP scope. A family persists as long as it has members.
6. **Onboarding flow integration** — a dedicated onboarding epic will wire together the full post-login experience (family creation as part of onboarding).
7. **Rate limiting** — deferred to security hardening epic.
8. **Audit logging** — deferred to security hardening epic.

## Design Considerations

- The `/family` page should follow the existing Chakra UI theme established in Epic 01/02.
- The "Create Family" view should be clean and minimal: centered card with family name input, timezone dropdown, and a create button.
- The member list should show each member's avatar (or initial), display name, email, and role badge (Admin/Member).
- The invite form should be a simple email input with a send button. The generic success toast ("If a user with that email exists, they will receive an invitation.") should always appear — never reveal whether the email matched a user.
- Role change and member removal should use confirmation dialogs to prevent accidental actions.
- The pending invites section should be prominent — either a banner at the top of the home page or a badge on the Family nav tab.
- Bottom navigation should use Chakra UI's tab or button group components with icons matching the PRD wireframe.

## Repository Standards

- **Backend**: Python 3.12+, FastAPI, async SQLAlchemy 2.0, Alembic for migrations, Pydantic for request/response schemas, structlog for logging, ruff for linting/formatting.
- **Frontend**: TypeScript, React 19, Vite, Chakra UI v3, React Query (TanStack), React Router v7, Vitest + React Testing Library, ESLint + Prettier.
- **Testing**: pytest with async support (`pytest-asyncio`), httpx `AsyncClient` for API tests, Vitest for frontend unit tests. Full testing pyramid per epic.
- **Docker**: All services run via Tilt (`task up`). Backend and frontend have hot-reload.
- **Code organization**: Backend code in `backend/app/` with `models/`, `schemas/`, `services/`, `routers/` subdirectories. Frontend code in `frontend/src/` with `pages/`, `components/`, `hooks/`, `api/` subdirectories.

## Technical Considerations

- **RBAC enforcement**: Implemented as FastAPI dependencies (`require_family_member`, `require_family_admin`) that compose with the existing `get_current_user` dependency. These should be reusable by all future family-scoped endpoints.
- **One-family constraint**: Enforced at the service layer (query `family_members` for existing membership). The unique constraint on `(family_id, user_id)` prevents duplicate memberships but does not enforce single-family.
- **Privacy-preserving invites**: The invite endpoint must always return the same response shape and HTTP status regardless of whether the email belongs to a registered user. This prevents user enumeration attacks.
- **FamilyContext pattern**: A React Context populated from the `/api/me` response's new `family` field. Downstream epics will use `useFamilyContext()` to get the family ID for scoping API calls.
- **Alembic migration**: Must be compatible with the existing users/refresh_token_blacklist migration from Epic 02. The new migration creates families, family_members, and invites tables.
- **SQLAlchemy relationships**: The `User` model should gain a `family_memberships` relationship. The `Family` model should have `members` (via family_members) and `invites` relationships for eager loading in the detail endpoint.
- **Test factories**: `create_test_family(db, user)` should create both the family and the admin membership in a single call. `create_test_invite(db, family, invited_user, invited_by)` should create a pending invite.

## Recommended Skills for Sub-Agents

The following installed skills should be made available to sub-agents during planning and execution:

| Skill | When to Use |
|-------|-------------|
| `fastapi-templates` | When implementing backend API endpoints, async patterns, and dependency injection for family/invite routers |
| `architecture-patterns` | When designing the FamilyService layer and RBAC dependency architecture |
| `test-driven-development` | When implementing any feature — write tests first, then implementation |
| `systematic-debugging` | When encountering test failures or integration issues |
| `vercel-react-best-practices` | When building React components for family pages, optimizing re-renders |
| `vercel-composition-patterns` | When designing reusable component APIs for member list, invite modal, role picker |
| `typescript-advanced-types` | When defining TypeScript types for family/invite/member API responses |
| `webapp-testing` | When running E2E browser tests of family management flows |

## Security Considerations

- **Privacy-preserving invites**: The invite endpoint MUST NOT reveal whether an email belongs to a registered user. Always return the same generic success message. This prevents user enumeration.
- **RBAC at application layer**: All family-scoped endpoints must use `require_family_member` or `require_family_admin` dependencies. Never rely on client-side role checks alone.
- **Owner protection**: The family creator (`created_by`) cannot be removed, cannot leave, and cannot be demoted from admin. This is a hard invariant.
- **Last-admin protection**: A family must always have at least one admin. Demoting the last admin is blocked.
- **404 vs 403 ambiguity**: For family endpoints, return 404 (not 403) when a user is not a member — do not reveal whether a family exists to non-members.
- **No secrets in invites**: Invite IDs are UUIDs but should only be accessible to the invited user. The `GET /api/invites` endpoint filters by `invited_user_id = current_user.id`.

## Success Metrics

1. **Family lifecycle works end-to-end**: A user can create a family, invite another user, that user can accept, and both see the shared member list
2. **RBAC is enforced**: Admin-only operations return 403 for members, member-only operations return 404 for non-members
3. **Privacy is preserved**: Inviting a non-existent email returns the same response as inviting a valid email
4. **All tests pass**: Backend and frontend tests pass via `task test`
5. **Frontend navigation works**: Bottom nav renders with Family tab, family pages are functional

## Open Questions

No open questions at this time. All key decisions were resolved in the clarifying questions round.
