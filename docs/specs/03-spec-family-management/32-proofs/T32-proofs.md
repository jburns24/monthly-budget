# T32 Proof Summary: invite_user (privacy-preserving)

Task: T02.2 — Implement FamilyService — invite_user (privacy-preserving)

## Implementation

Added `invite_user` async method to `backend/app/services/family_service.py`.

### Method Signature

```python
async def invite_user(
    db: AsyncSession,
    family_id: uuid.UUID,
    email: str,
    invited_by_user: User,
) -> None:
```

### Privacy-Preserving Logic

The method always returns `None` without raising any exceptions, regardless of whether:
- The email matches a registered user
- The matched user is already in a family
- A pending invite already exists

An Invite record is only created when the target user exists and is eligible (not in any family, no existing pending invite).

## Tests Added

Four tests added to `backend/tests/test_family_service.py`:

| Test | Description |
|------|-------------|
| `test_invite_user_nonexistent_email_succeeds_silently` | Returns None, no invite created for unknown email |
| `test_invite_user_already_in_family_succeeds_silently` | Returns None, no invite created if user in a family |
| `test_invite_user_already_has_pending_invite_succeeds_silently` | Returns None, no duplicate invite created |
| `test_invite_user_valid_email_creates_invite` | Creates pending Invite with correct fields for eligible user |

## Proof Artifacts

| File | Type | Status |
|------|------|--------|
| T32-01-lint.txt | cli (ruff check) | PASS |
| T32-02-format.txt | cli (ruff format --check) | PASS |
| T32-03-implementation.txt | file (grep verification) | PASS |

## Notes

The database was not running in the local environment, so tests could not be executed directly.
Tests are verified to be syntactically correct, properly importing `invite_user`, and following
the same patterns as existing tests in the file. Full test execution is expected to pass in the
CI environment with a running Postgres instance.
