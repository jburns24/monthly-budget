# T27 Proof Summary — FIX-REVIEW: Low-confidence expense must be amount_cents=0 per spec

- Task: 27
- Owner: worker-4
- Category: C (Spec Compliance)
- Severity: blocking
- Completed: 2026-04-19
- Model: opus

## Spec mapping

07-spec-receipt-scanning-claude-ai.md §Unit 3 FR states:

> Claude `low` confidence → 201 with expense created (`amount_cents=0`) and
> `needs_edit: true`.

§Unit 5 keys the frontend "Needs review" chip on
`receipt_status === 'completed' && amount_cents === 0`, which could never fire
while the service wrote `amount_cents=1` as a CHECK-constraint workaround.

## Changes

1. New Alembic revision `e8b1c9f7a321_relax_expenses_amount_check_for_receipts.py`
   drops the `ck_expenses_amount_positive CHECK (amount_cents > 0)` and re-adds
   it as `CHECK (amount_cents >= 0)`. Downgrade restores `> 0`.
2. `backend/app/models/expense.py` updates the ORM `CheckConstraint` to mirror
   the relaxed predicate and documents the intent (receipt scan placeholder).
3. `backend/app/services/receipt_service.py` `_run_phase3` no longer falls back
   to `amount_cents=1`; it sets `amount_cents=0` whenever `needs_edit` is true
   (low confidence OR Claude omitted a total).
4. Test updates:
   - `tests/test_receipt_service.py`:
     - Updated `test_success_low_confidence_needs_edit_true` to assert `== 0`.
     - Updated `test_success_no_total_needs_edit_true` to assert `== 0`.
     - Added regression `test_low_confidence_with_valid_total_still_persists_amount_zero`.
   - `tests/test_expenses_models.py`:
     - Renamed `_rejects_zero` -> `_allows_zero`; asserts the insert now succeeds.
   - `tests/test_migrations.py`:
     - Cleans zero-amount rows and downgrades to the explicit pre-receipts
       revision, so the round-trip assertion is robust when more migrations
       stack on top.

## Proof artifacts

| File | Type | Status |
|------|------|--------|
| `27-01-test.txt` | pytest run of `tests/test_receipt_service.py + tests/test_receipts_api.py` | PASS (40 passed) |
| `27-02-cli.txt`  | `alembic upgrade head` + psql verification of relaxed CHECK constraint | PASS |
| `27-03-spec-coverage.txt` | Targeted run of the three tests that cover §Unit 3 | PASS (3 passed) |

## Pre-existing failures NOT introduced by this task

When running the full backend suite, 15 tests in
`tests/test_categories_integration.py`, `tests/test_family_integration.py`,
`tests/test_rbac_dependencies.py`, and `tests/test_users.py` fail when executed
together but pass individually (test-ordering pollution on `jwt_secret`). These
failures existed before this task and are unrelated to the receipts CHECK
constraint or `_run_phase3` changes.

## Commands

```bash
# Apply migration
cd backend && uv run alembic upgrade head

# Run impacted tests
cd backend && uv run pytest tests/test_receipt_service.py tests/test_receipts_api.py tests/test_expenses_models.py tests/test_migrations.py -v

# Verify CHECK constraint in the live DB
docker exec monthly-budget-db psql -U monthly_budget -d monthly_budget \
  -c "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_expenses_amount_positive';"
```
