# Task 30 Proof Summary — Atomic failed→processing transition on retry

**Task:** 30 (FIX-REVIEW-30: ISSUE-5 — Retry endpoint lacks atomic
`failed→processing` transition)
**Category:** A (Correctness / Concurrency)
**Severity:** blocking
**Date:** 2026-04-19
**Status:** COMPLETED

## Issue

`POST /api/families/{family_id}/receipts/{receipt_id}/retry` only rejected
`status='completed'` rows with 409. Two concurrent retries on a *failed*
receipt could therefore both pass the check and both invoke
`reprocess_receipt`, meaning the Claude call was made twice — doubling cost,
creating a duplicate-Expense race, and violating the spec's Open Question #2
proposal for optimistic locking via the `receipts.status` column.

## Fix

Added `receipt_service.claim_receipt_for_retry(db, receipt)` which issues a
single

```sql
UPDATE receipts
   SET status='processing', error_message=NULL
 WHERE id = :id
   AND status = 'failed'
```

inside a `begin_nested` savepoint.

- **Winner** (`rowcount == 1`): savepoint + outer transaction commit, row is
  now `processing` and visible to any concurrent session.
- **Loser** (`rowcount == 0`): savepoint rolls back, service re-reads the
  current status, and raises `HTTPException(409, "Receipt cannot be retried
  from status '<status>'.")`.

The PostgreSQL row lock held by the winning UPDATE serializes concurrent
retries at the database layer, so exactly one caller can transition the row
out of `failed` — the other sees `rowcount = 0` and 409s.

The router (`backend/app/routers/receipts.py`) now delegates the 409 decision
to the service and no longer hand-checks `receipt.status == "completed"`.
This also tightens 409 coverage to every non-`failed` status (including an
in-flight `processing` from the initial upload).

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/receipt_service.py` | Added `claim_receipt_for_retry` helper using `UPDATE ... WHERE status='failed'` inside a savepoint. Updated `reprocess_receipt` docstring to document the required preceding claim. Added `select`, `update` imports. |
| `backend/app/routers/receipts.py` | Retry handler now calls `claim_receipt_for_retry` instead of the local `if receipt.status == "completed"` guard; docstring cites spec Open Question #2. |
| `backend/tests/test_receipts_api.py` | Added 3 regression tests: `test_retry_processing_receipt_returns_409` (new 409 surface for `processing`), `test_retry_uses_atomic_failed_to_processing_update` (service-layer spy proves the claim commits before `reprocess_receipt`), `test_retry_concurrent_only_one_succeeds` (two sessions race on the same row; second must 409). |

## Proof Artifacts

| # | Type | File | Status | Notes |
|---|------|------|--------|-------|
| 1 | test | `30-01-test.txt` | PASS | 5/5 retry tests pass (2 pre-existing + 3 new) |
| 2 | cli  | `30-02-cli.txt`  | PASS | `git diff` shows router delegates to `claim_receipt_for_retry` and service adds the atomic UPDATE helper |
| 3 | cli  | `30-03-cli.txt`  | PASS | `ruff check` + `ruff format --check` clean on all modified files |

## Verification

```bash
cd backend && uv run pytest \
  tests/test_receipts_api.py::test_retry_completed_receipt_returns_409 \
  tests/test_receipts_api.py::test_retry_failed_receipt_returns_200 \
  tests/test_receipts_api.py::test_retry_processing_receipt_returns_409 \
  tests/test_receipts_api.py::test_retry_uses_atomic_failed_to_processing_update \
  tests/test_receipts_api.py::test_retry_concurrent_only_one_succeeds -v
# 5 passed

cd backend && uv run pytest tests/test_receipts_api.py tests/test_receipt_service.py \
  tests/test_receipt_storage.py tests/test_receipt_model.py
# 78 passed (full receipt suite, no regressions)
```

## Spec Traceability

- Spec §Open Questions #2: "Proposed: use optimistic locking via
  `receipts.status` — only allow retry when `status='failed'`; transition
  to `processing` atomically in a savepoint."
- Review ISSUE-5 (Category A): "Use `UPDATE ... WHERE status='failed'
  RETURNING ...` (or `SELECT ... FOR UPDATE` in a savepoint); return 409 on
  any non-`failed` status."

Both requirements are satisfied by the implementation.
