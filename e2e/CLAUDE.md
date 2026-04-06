# E2E Tests — CLAUDE.md

Playwright 1.44 with TypeScript, running against local backend (:8000) and frontend (:5173).

## Commands

```bash
npx playwright test                # Run all tests (headless)
npx playwright test --headed       # Run with visible browser
npx playwright test --ui           # Interactive UI mode
npx playwright test tests/expenses.spec.ts  # Single spec file
```

Locally, Tilt keeps services running (`reuseExistingServer: true`). In CI, Playwright auto-starts backend and frontend.

## Architecture

- **Config**: `playwright.config.ts` — sequential execution, single worker, setup project dependency
- **Tests**: `tests/*.spec.ts` — auth, expenses, categories, family, monthly-goals, invite
- **Setup**: `tests/auth.setup.ts` — authenticates via dev-login, saves storage state to `playwright/.auth/user.json`
- **Page Objects**: `pages/*.page.ts` — DashboardPage, ExpensesPage, CategoriesPage, FamilyPage, LoginPage
- **Fixtures**: `fixtures/auth.ts` (multi-user context), `fixtures/test-data.ts` (API factory functions)

## Critical Patterns

**Sequential execution**: `fullyParallel: false` with `workers: 1`. Tests share database state and MUST run in order within a spec file. The setup project runs first, then chromium tests depend on it.

**Page Object Model**: All page interactions go through page object classes in `pages/`. Each class encapsulates locators and actions. When adding new UI interactions, add methods to the relevant page object.

**Test data via API**: Tests seed data through backend API calls, not through the UI. Use factory functions from `fixtures/test-data.ts`:
- `resetTestData(request)` — truncates all test tables (respects FK order). Call in `beforeAll`/`beforeEach`.
- `loginAs(playwright, email, displayName)` — creates user via dev-login, returns authenticated `APIRequestContext`
- `createFamilyViaApi()`, `createCategoryViaApi()`, `createExpenseViaApi()`, `createMonthlyGoalViaApi()`, `sendInviteViaApi()`

**Multi-user scenarios**: Import `test` from `fixtures/auth.ts` (not from `@playwright/test`) to get the `userBContext` fixture for a second authenticated user.

**Auth flow**: The setup project (`auth.setup.ts`) authenticates once and persists state to `playwright/.auth/user.json`. All chromium tests reuse this state via `storageState` config.

## Hard Stops

- NEVER set `fullyParallel: true` or increase `workers` — tests depend on sequential DB state
- NEVER interact with the database directly — always use the API factory functions in `fixtures/test-data.ts`
- NEVER skip `resetTestData()` in test setup — tests assume a clean database
- NEVER add page interactions directly in spec files — add methods to the appropriate page object in `pages/`
- NEVER import `test` from `@playwright/test` in multi-user specs — use the fixture from `fixtures/auth.ts`
