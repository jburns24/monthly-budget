# T35 Proof Summary — Pydantic Schemas for Family API

## Task
T03.1: Create Pydantic schemas for family API request/response models

## Files Created/Modified
- `backend/app/schemas/family.py` — new file with all 9 schema classes
- `backend/app/schemas/user.py` — added `family: FamilyBrief | None = None` field to `UserResponse`
- `backend/pyproject.toml` — added `email-validator>=2.1.0` dependency (required for `EmailStr`)

## Schemas Implemented
| Schema | Purpose |
|---|---|
| `FamilyCreate` | POST /api/families request body |
| `FamilyMemberResponse` | Nested member in FamilyResponse |
| `FamilyResponse` | Full family with members |
| `FamilyBrief` | Abbreviated family info in /api/me |
| `InviteCreate` | Send invite request (EmailStr validated) |
| `InviteResponse` | Invite details response |
| `InviteAction` | Accept/decline invite (Literal) |
| `RoleUpdate` | Change member role (Literal admin/member) |
| `GenericMessage` | Generic success message |

## Proof Artifacts
| File | Type | Status |
|---|---|---|
| T35-01-schema-validation.txt | cli | PASS |
| T35-02-user-schema-family-field.txt | cli | PASS |
| T35-03-lint-check.txt | cli | PASS |

## Notes
- `email-validator` package was not in pyproject.toml; added it since `EmailStr` is a first-class requirement.
- Pre-existing test failures (19 database-related tests) are unrelated to this task — they require a running PostgreSQL instance.
- All 3 proof artifacts pass.
