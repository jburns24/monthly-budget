# 00 Questions Round 1 - Epic Breakdown

The PRD covers a full-stack household budget application. It is **too large for a single spec** and needs to be split into multiple epics. Below is a proposed breakdown into 9 epics, each sized as a "just right" spec for the SDD workflow.

Please review, adjust, and answer the questions below.

---

## Proposed Epic Breakdown

| # | Epic | Key PRD Sections | Dependencies |
|---|------|-------------------|--------------|
| 01 | **Project Scaffolding & Infrastructure** | §7 Architecture, §17 Containers, §18 Dev Experience | None |
| 02 | **Authentication (Google OAuth + JWT)** | §9 Auth, §8 Security (T1, T7, T11) | Epic 01 |
| 03 | **Family Management & RBAC** | §4 Families, §5 Family Permissions, §9.3 RBAC | Epic 02 |
| 04 | **Categories Management** | §4 Categories, §10 Schema (categories table) | Epic 03 |
| 05 | **Manual Expense Entry & Dashboard** | §4 Expense Entry (Manual), §6 UX Flows 1-2, §12 Budget Dashboard API | Epic 04 |
| 06 | **Monthly Goals & Budget Progress** | §4 Monthly Goals, §6.3 Dashboard wireframe, §14 Rollover | Epic 04 |
| 07 | **Receipt Scanning (Claude AI)** | §4 Receipt Photo, §13 Receipt Pipeline, §5 Receipt edge cases | Epic 05 |
| 08 | **CSV Export** | §4 CSV Export, §15 CSV Spec | Epic 05 |
| 09 | **PWA & Offline Support** | §7.2 PWA stack, §6.4 Mobile principles | Epic 05 |

---

## 1. Epic Granularity

Does this breakdown feel right, or would you prefer to combine or split any epics?

- [x] (A) This breakdown looks good as-is
- [ ] (B) Combine Epics 04 (Categories) and 06 (Monthly Goals) — they're closely related
- [ ] (C) Combine Epics 05 (Manual Expense) and 06 (Goals) — the dashboard needs both to be useful
- [ ] (D) Split Epic 05 further — separate "Expense CRUD API" from "Dashboard UI"
- [ ] (E) Other (describe)

## 2. Implementation Order

The proposed order above follows dependency chains. Would you prefer a different prioritization?

- [x] (A) Follow the proposed order (01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 → 09)
- [ ] (B) Prioritize the "happy path" first: Auth → Expense Entry → Receipt Scan, defer Family/RBAC complexity
- [ ] (C) Start with the riskiest piece first (Receipt Scanning) to validate Claude API integration early
- [ ] (D) Other (describe)

## 3. Infrastructure Scope (Epic 01)

How much infrastructure should Epic 01 cover?

- [x] (A) Full Docker Compose stack (API + DB + Redis + Caddy) + DB migrations + project scaffolding — "docker compose up" works end-to-end with health checks
- [ ] (B) Minimal: just project structure, Docker Compose with DB only, basic FastAPI app + React app with Vite — enough to start coding
- [ ] (C) Backend-only first: FastAPI + PostgreSQL + Redis + Alembic migrations. Frontend scaffolding in a separate epic
- [ ] (D) Other (describe)

## 4. Onboarding Flow Ownership

The onboarding flow (§6.2 Flow 1) spans multiple epics (auth, family creation, categories, first expense). Where should it live?

- [ ] (A) Spread across epics — each epic implements its piece of onboarding (auth screen in Epic 02, family creation in Epic 03, etc.)
- [x] (B) Dedicated onboarding epic after the core features are built — wires together the full flow
- [ ] (C) Include the full onboarding flow in Epic 05 (Manual Expense) since that's the end goal of onboarding
- [ ] (D) Other (describe)

## 5. Security & Audit Logging

The PRD has extensive security requirements (§8 STRIDE, §11 RLS, §21 Audit Logging). How should these be handled?

- [ ] (A) Bake security into each epic — RLS policies ship with the tables they protect, audit logging ships with each feature
- [x] (B) Separate security hardening epic at the end — get features working first, then layer on RLS, audit logging, rate limiting
- [ ] (C) Hybrid: RLS and basic auth checks in each epic, but audit logging + rate limiting as a dedicated epic
- [ ] (D) Other (describe)

## 6. Testing Strategy Per Epic

What level of testing should each epic include?

- [ ] (A) Unit + integration tests per epic. E2E tests (Playwright) in a final polish epic
- [x] (B) Full testing pyramid per epic (unit + contract + integration + relevant E2E flows)
- [ ] (C) Minimal testing per epic (happy path only). Comprehensive testing as a dedicated epic
- [ ] (D) Other (describe)

## 7. Which Epic Should We Spec First?

Once we agree on the breakdown, which epic do you want to spec first?

- [x] (A) Epic 01 — Project Scaffolding & Infrastructure (start from the ground up)
- [ ] (B) Epic 02 — Authentication (need this before anything else works)
- [ ] (C) Epic 05 — Manual Expense Entry (jump to the core value proposition)
- [ ] (D) All of them — generate all 9 specs in sequence
- [ ] (E) Other (describe)
