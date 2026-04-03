# T30 Proof Summary — T01.3: Write model unit tests for Family, FamilyMember, and Invite

## Task

Write unit tests verifying ORM models map correctly to the schema and that constraints are enforced.

**File created:** `backend/tests/test_family_models.py`

## Proof Artifacts

| # | File | Type | Status |
|---|------|------|--------|
| 1 | T30-01-test.txt | test | PASS |
| 2 | T30-02-cli.txt | cli | PASS |

## Tests Written (11 total)

| Test | Verifies |
|------|----------|
| `test_create_family` | Family columns persist correctly, FK to users |
| `test_family_defaults` | timezone defaults to America/New_York, edit_grace_days to 7 |
| `test_create_family_member` | FamilyMember columns and FK relationship to Family |
| `test_family_member_unique_constraint` | Duplicate (family_id, user_id) raises IntegrityError |
| `test_family_member_role_check` | Invalid role value raises IntegrityError |
| `test_create_invite` | Invite columns and nullable responded_at |
| `test_invite_status_check` | Invalid status value raises IntegrityError |
| `test_invite_unique_constraint` | Duplicate (family_id, invited_user_id, status) raises IntegrityError |
| `test_user_family_memberships_relationship` | User.family_memberships returns related FamilyMember records |
| `test_family_members_relationship` | Family.members returns related FamilyMember records |
| `test_family_cascade_delete` | Deleting a Family cascades to family_members and invites |

## Result

All 11 tests PASS. Lint clean (ruff).
