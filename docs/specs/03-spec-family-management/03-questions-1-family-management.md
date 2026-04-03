# 03 Questions Round 1 — Family Management & RBAC

## 1. One-Family Constraint

Should the API enforce one family per user?

- [x] (A) Strict one-family — enforce at the API level. Matches PRD edge case.
- [ ] (B) Allow multiple families — prepare for future multi-family support.

## 2. Invite Flow

How should admin invites work?

- [x] (A) Email lookup — admin enters an email. System checks if user exists internally. **Privacy-preserving:** response always confirms "Invite sent" without revealing whether the email matches a registered user.
- [ ] (B) User search/select — admin searches registered users.

**User note:** The admin should always see a generic success message that does not confirm whether the email belongs to a valid user.

## 3. Frontend Navigation

- [x] (A) Bottom nav tab — add `/family` route as a new tab matching PRD wireframe.
- [ ] (B) Settings sub-page
- [ ] (C) Defer frontend

## 4. Row-Level Security

- [x] (A) Defer RLS — per epic breakdown decision, enforce access at application layer only.
- [ ] (B) Include basic RLS in this epic.
