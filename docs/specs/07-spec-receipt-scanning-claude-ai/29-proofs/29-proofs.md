# Task 29 Proofs — Decompression-bomb dimension pre-check

## Task

FIX-REVIEW (Category B: Security) — Add a dimension pre-check before
`Image.load()` in `backend/app/services/receipt_storage.py:sanitize_image`
so that crafted images under `MAX_IMAGE_PIXELS` but with extreme aspect
ratio (e.g. 4096×62499) are rejected before any pixel decode.

## Change Summary

- `backend/app/services/receipt_storage.py`
  - Added module constant `_MAX_INPUT_DIMENSION = 4000`
  - In `sanitize_image`, after `Image.open(...)` and before `base.load()`,
    raise `ValueError("Image dimensions exceed limit: ...")` when
    `base.width > _MAX_INPUT_DIMENSION or base.height > _MAX_INPUT_DIMENSION`.
  - Updated docstring to document the new raise path.
- `backend/tests/test_receipt_storage.py`
  - Added `test_sanitize_rejects_extreme_width_before_load` (4001×100 rejected)
  - Added `test_sanitize_rejects_extreme_height_before_load` (100×4001 rejected)
  - Added `test_sanitize_allows_dimension_at_limit` (4000×4000 still accepted)

## Proof Artifacts

| Artifact | Type | Status |
| --- | --- | --- |
| `29-01-test.txt` | test | PASS — 21 passed, 1 warning |
| `29-02-cli.txt` | cli  | PASS — diff shows dimension guard before `base.load()` |

## Verification

```
cd backend && uv run pytest tests/test_receipt_storage.py -v
# 21 passed (18 existing + 3 new regression tests)
cd backend && uv run ruff check app/services/receipt_storage.py tests/test_receipt_storage.py
# All checks passed
```

## Why this matters

`MAX_IMAGE_PIXELS` alone is not sufficient protection: a 4096×62499 JPEG
has ~256 MP and would still trigger Pillow to allocate a very tall decoded
buffer. The dimension pre-check is a cheap header-only inspection that
runs before `base.load()` forces the full pixel decode, closing the
decompression-bomb attack surface identified in the spec's Technical
Considerations.
