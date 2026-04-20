# T28 Proof Summary — Add required text block to Claude user message

- **Task**: FIX-REVIEW: Add required text block to Claude user message
- **Category**: C (Spec Compliance)
- **Severity**: blocking
- **Status**: COMPLETED
- **Owner**: worker-2
- **Timestamp**: 2026-04-19

## Spec reference

Spec Unit 2 (`07-spec-receipt-scanning-claude-ai.md` line 60):

> a single user message combining the base64 image and a "Extract structured data from this receipt image." text block

PRD §13 canonical shape (from `07-research-receipt-scanning-claude-ai.md` lines 499-502):

```python
messages=[{"role": "user", "content": [
    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
    {"type": "text", "text": "Extract structured data from this receipt image."},
]}]
```

## Files changed

- `backend/app/services/claude_client.py`
  - Added `_USER_TEXT_PROMPT = "Extract structured data from this receipt image."` module constant (next to `_SYSTEM_PROMPT`)
  - Appended `{"type": "text", "text": _USER_TEXT_PROMPT}` to the user message `content` list in `_call_claude`, so content is now exactly `[image_block, text_block]` per PRD §13
- `backend/tests/test_claude_client.py`
  - Added `test_extract_receipt_builds_correct_request` — the proof-artifact test named in the task metadata. Asserts the full PRD §13 shape: model, max_tokens, system prompt, tool_choice, a single user message, and a content list of exactly `[image_block, text_block]` with the literal `"Extract structured data from this receipt image."` text.

## Proof artifacts

| # | File | Type | Status |
|---|------|------|--------|
| 1 | `T28-01-test.txt` | test (proof_artifacts[0] from task metadata) | PASS |
| 2 | `T28-02-test.txt` | test (verification.post full-file regression) | PASS |

Both proof commands return exit code 0.

- Artifact 1: `tests/test_claude_client.py::test_extract_receipt_builds_correct_request` — 1 passed.
- Artifact 2: `tests/test_claude_client.py` full file — 13 passed (12 pre-existing + 1 new; no regressions).

## Lint

`uv run ruff check app/services/claude_client.py tests/test_claude_client.py` — All checks passed!

## Scope discipline

Only files in `metadata.scope.files_to_modify` (`backend/app/services/claude_client.py`) plus the single proof-artifact test file named in the task description (`backend/tests/test_claude_client.py::test_extract_receipt_builds_correct_request`) were modified. The task description explicitly authorizes updating the test file (see "Suggested Fix"). No other workers' scopes were touched.
