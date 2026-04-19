# T01 Proof Summary — Receipts Data Layer

## Task
T01: Land the `receipts` table, FK on `expenses.receipt_id`, `pg_trgm` extension, SQLAlchemy model, Pydantic schemas, and test factory.

## Proof Results

| # | Type | Artifact | Status |
|---|------|----------|--------|
| 1 | test | T01-01-test.txt — `test_receipt_model.py` 14 tests | PASS |
| 2 | test | T01-02-test.txt — `test_migrations.py::test_c4e2f1b3d5a8_upgrade_downgrade` | PASS |
| 3 | cli  | T01-03-cli.txt — `alembic upgrade head && \d+ receipts` | PASS |
| 4 | file | T01-04-file.txt — migration file exists with upgrade/downgrade | PASS |

## Files Created/Modified

### New files
- `backend/app/models/receipt.py` — SQLAlchemy Receipt model
- `backend/app/schemas/receipt.py` — Pydantic schemas (ReceiptStatus, ExtractedReceipt, ReceiptResponse, ReceiptUploadResponse, ReceiptListQuery)
- `backend/alembic/versions/c4e2f1b3d5a8_add_receipts_and_pg_trgm.py` — Alembic migration
- `backend/tests/test_receipt_model.py` — 14 ORM model tests
- `backend/tests/test_migrations.py` — migration round-trip test

### Modified files
- `backend/app/models/__init__.py` — added Receipt import
- `backend/app/models/expense.py` — added `receipt` relationship + `receipt_status` property
- `backend/app/models/family.py` — added `receipts` relationship
- `backend/app/models/user.py` — added `uploaded_receipts` relationship
- `backend/app/schemas/expense.py` — added `receipt_id` and `receipt_status` to ExpenseResponse
- `backend/tests/conftest.py` — added `create_test_receipt` factory function

## Key Decisions
- Used `foreign(Expense.receipt_id) == Receipt.id` primaryjoin for the one-to-one via non-FK column
- `receipt_status` exposed as `@property` on Expense model for seamless Pydantic serialization
- Migration test uses `.venv/bin/alembic` directly to avoid local `alembic/` dir import shadowing
