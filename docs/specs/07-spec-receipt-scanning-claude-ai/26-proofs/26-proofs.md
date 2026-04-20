# Task 26 Proof Summary — Persist receipt row on failure

**Task:** 26 (FIX-REVIEW: Persist receipt row on failure — rollback swallows `_mark_failed`)
**Category:** A (Correctness)
**Severity:** blocking
**Date:** 2026-04-19
**Status:** COMPLETED

## Issue

When Phase 2 (Claude API call) or Phase 3 (DB write of Expense) raised an
`HTTPException`, FastAPI's `get_db()` dependency would roll back the entire
outer session. That discarded both the Phase-1 `Receipt(status='processing')`
INSERT and the `_mark_failed` savepoint UPDATE. The receipt row never landed in
the database, yet the sanitized image remained on disk (the Claude-error branch
keeps the file so a retry is possible). Net result: orphaned image + no audit
row, breaking the spec's "Receipt row persists for audit" guarantee and
defeating the retry flow.

## Fix

`backend/app/services/receipt_service.py::_mark_failed` now explicitly
`await db.commit()`s after the nested savepoint writes the `status='failed'`
update. This makes the failed audit row durable before the caller raises an
`HTTPException`. The subsequent rollback inside `get_db()` becomes a no-op on
an already-committed transaction, so the row persists.

The image-deletion behaviour is unchanged:
- Claude-error branches pass `image_path=None` so the file is preserved for
  the retry endpoint.
- Non-receipt and Phase-3 DB-error branches still pass the `image_path`, so
  the file is removed.

## Artifacts

| File | Type | Status | Description |
|------|------|--------|-------------|
| 26-01-test.txt | test | PASS | 20/20 tests pass (`test_failed_receipt_image_cleaned_up` + `test_receipt_service.py`) |
| 26-02-regression.txt | test (regression) | PASS | Regression test correctly FAILS without fix, PASSES with fix |

## Commands

```bash
cd backend && uv run pytest \
  tests/test_receipts_api.py::test_failed_receipt_image_cleaned_up \
  tests/test_receipt_service.py -v
```

Result: `20 passed in 1.00s` (see `26-01-test.txt`).

## Files Changed

- `backend/app/services/receipt_service.py` — added `await db.commit()` in `_mark_failed` plus docstring explaining why the durability is required.
- `backend/tests/test_receipts_api.py` — added `test_failed_receipt_image_cleaned_up` regression test plus `select` import; the test uses a `production_like_get_db` override that faithfully mirrors `app.database.get_db`'s commit-on-success / rollback-on-exception contract so the production rollback path is exercised. Also asserts the image file is preserved (not deleted) for Claude-error branches so the retry endpoint can re-run extraction.
