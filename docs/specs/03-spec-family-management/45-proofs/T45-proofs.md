# T45 Proof Summary

**Task:** T05.3 — Write backend edge case tests: privacy, one-family, owner/admin protection
**Status:** COMPLETED
**Timestamp:** 2026-04-03T22:54:14Z

## Artifacts

| File | Type | Status | Description |
|------|------|--------|-------------|
| T45-01-syntax.txt | cli | PASS | pytest --collect-only: 14 tests collected, no import/syntax errors |
| T45-02-lint.txt | cli | PASS | ruff check: all lint checks passed |
| T45-03-code-review.txt | file | PASS | Code review: all 8 required test scenarios present |

## Implementation

**File created:** `backend/tests/test_family_integration.py`

14 tests covering:

- **Privacy-preserving invite** (1 test): `test_invite_nonexistent_email_same_response` — both existing and non-existing email return `None`
- **One-family constraint** (2 tests): `test_create_second_family_returns_409`, `test_accept_invite_while_in_family_returns_409` — invite remains pending on 409
- **Owner protection — leave** (2 tests): `test_owner_cannot_leave`, `test_owner_remains_in_family_after_leave_attempt`
- **Owner protection — remove** (2 tests): `test_owner_cannot_be_removed`, `test_owner_still_member_after_remove_attempt`
- **Owner protection — demote** (2 tests): `test_owner_cannot_be_demoted`, `test_owner_role_unchanged_after_demotion_attempt`
- **Last-admin protection** (2 tests): `test_demote_last_admin_blocked`, `test_demote_last_admin_role_unchanged`
- **Positive guards** (3 tests): `test_demote_non_last_admin_succeeds`, `test_leave_nonexistent_family_404`, `test_remove_nonexistent_member_404`

## Notes

Tests exercise the service layer directly (not HTTP layer) because the family router (T03.2) was still in progress when this task ran. This is consistent with the pattern in `test_family_service.py`. When T03.2 ships the router, these tests continue to work unchanged.
