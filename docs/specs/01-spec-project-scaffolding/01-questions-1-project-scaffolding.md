# 01 Questions Round 1 - Project Scaffolding & Infrastructure

Please answer each question below. These inform the spec for Epic 01: getting `docker compose up` to a working, healthy full-stack setup.

## 1. Node.js Package Manager

Which package manager for the React frontend?

- [x] (A) npm (standard, no extra install)
- [ ] (B) pnpm (faster, disk-efficient)
- [ ] (C) yarn (classic v1)
- [ ] (D) No preference — pick the best fit

## 2. Python Dependency Management

Which tool for backend dependency management?

- [ ] (A) pip + requirements.txt (simple, matches PRD)
- [ ] (B) Poetry + pyproject.toml (lockfile, dependency resolution)
- [x] (C) uv + pyproject.toml (fast Rust-based pip replacement)
- [ ] (D) No preference — pick the best fit

## 3. Database Migrations in Epic 01

The PRD defines the full schema (§10). How much of it should Epic 01's initial migration include?

- [ ] (A) Full schema from the PRD — all tables, indexes, RLS functions (even though RLS enforcement comes later in the security epic)
- [ ] (B) Just the `users` table — each subsequent epic adds its own migrations
- [ ] (C) Tables needed through Epic 05 (users, families, family_members, categories, expenses, receipts, monthly_goals) — minimize future migration churn
- [x] (D) No tables — just Alembic setup with an empty initial migration. Each epic owns its migrations entirely

## 4. Caddy Reverse Proxy

The PRD specifies Caddy for reverse proxy + TLS. Should Epic 01 include Caddy in Docker Compose?

- [ ] (A) Yes — Caddy in front of both the API and Vite dev server, mimicking production routing
- [x] (B) No — just expose FastAPI (port 8000) and Vite (port 5173) directly in dev. Caddy comes in a deployment/production epic
- [ ] (C) Caddy for the API only, Vite dev server runs standalone with proxy config

## 5. .env.example Contents

What should the `.env.example` files include for Epic 01?

- [x] (A) All secrets from the PRD (Google OAuth, Anthropic API key, JWT secret, DB password, Redis password) — with placeholder values
- [ ] (B) Only what's needed for Epic 01 to run (DB password, Redis password) — add others as epics need them
- [ ] (C) All secrets with a script that auto-generates random values for local dev

## 6. Health Check Depth

The PRD mentions `/api/health` and `/api/health/ready`. What should Epic 01's health checks verify?

- [x] (A) Full: API running + DB connectable + Redis connectable + migrations current
- [ ] (B) Basic: API running + DB connectable (Redis check comes when we need Redis in later epics)
- [ ] (C) Minimal: API returns 200 on `/health` (just proves the container is up)

## 7. Frontend Starting Point

How much frontend scaffolding should Epic 01 include?

- [x] (A) Vite + React + TypeScript + Chakra UI + React Router + TanStack Query — all wired up with a placeholder "Hello World" page
- [ ] (B) Just Vite + React + TypeScript — add libraries as epics need them
- [ ] (C) Full scaffold from (A) plus PWA plugin (vite-plugin-pwa) configured with basic manifest and service worker

## 8. Observability in Epic 01

The PRD specifies Prometheus metrics and structured logging (§20). Include in scaffolding?

- [x] (A) Yes — structured JSON logging (structlog) + Prometheus metrics endpoint from day one
- [ ] (B) Structured logging only — metrics come later
- [ ] (C) Standard Python logging — observability is a later concern
- [ ] (D) No preference

## 9. CI/CD in Epic 01

Should Epic 01 include any CI pipeline setup?

- [x] (A) GitHub Actions: lint + type-check + test on PR (both backend and frontend)
- [ ] (B) Just linter configs (ruff, prettier, eslint) — CI pipeline in a later epic
- [ ] (C) Full CI/CD including Docker image build + push
- [ ] (D) No CI — purely local development for now

## 10. "It Works" Proof Artifact

What should the proof look like when Epic 01 is complete?

- [x] (A) `docker compose up` starts all services, `/api/health` returns 200 with DB/Redis status, frontend loads in browser at localhost
- [ ] (B) Same as (A) plus a screenshot/recording of the running stack
- [ ] (C) Same as (A) plus a simple API endpoint (e.g., `GET /api/v1/ping`) that reads from DB and returns a response, proving the full request path works
- [ ] (D) Other (describe)
