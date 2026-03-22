# Monthly Budget — Product Requirements Document

**Version:** 1.0
**Date:** 2026-03-22
**Status:** Final (Synthesized from PRD Arena — 4 competing drafts, 3 independent judges)

---

## 1. Problem Statement and Motivation

Household budget management is trapped on desktop spreadsheets. Families need to log expenses at the point of purchase — standing in a grocery store, splitting a dinner check, snapping a photo of a receipt in the parking lot. The gap between spending and recording kills adherence: by the time someone sits down at a computer, receipts are lost and expenses are forgotten.

Meanwhile, commercial budget apps sacrifice control for convenience. Cloud-hosted tools require handing financial data to third parties, paying recurring subscriptions, and accepting feature decisions made for mass markets rather than individual households.

### Competitive Landscape

The household budget market fragmented after Mint's shutdown in March 2024. The landscape now splits into three tiers:

| Category | Tools | Strengths | Gaps Monthly Budget Fills |
|----------|-------|-----------|---------------------------|
| **Premium Cloud** | YNAB ($109/yr), Monarch Money ($100/yr), Copilot ($95/yr) | Polished UX, bank sync, AI categorization | Expensive, cloud-only, no data sovereignty |
| **Freemium Cloud** | Rocket Money, Lunch Money ($10/mo), Goodbudget | Lower cost, specific strengths | Still cloud-hosted, limited family features |
| **Self-Hosted OSS** | Actual Budget, Firefly III, BudgetZero | Free, data ownership | No receipt scanning, weak mobile UX, no family collaboration |

**Key gaps Monthly Budget exploits:**
- No self-hosted tool has receipt scanning (Monarch Money is the only budget app with receipt OCR — at $100/yr cloud-only)
- Self-hosted mobile UX is poor (Firefly III: 795 MiB Docker image, desktop-first layout on mobile)
- Family collaboration in self-hosted tools is primitive (no role-based access, no shared goals)

**Why now:** AI receipt parsing (Claude vision API) is production-ready at ~$0.01/receipt. PWA capabilities (camera access, offline support, installability) have matured to near-native quality. Post-Mint migration is ongoing with growing interest in privacy-respecting, self-hosted options.

— *Competitive analysis: Worker Delta. Problem framing: Worker Bravo.*

---

## 2. Target Users / Personas

### Persona 1: Sarah — The Budget Owner
- **Age:** 34, working parent
- **Tech comfort:** Uses apps daily but not a developer
- **Pain:** "I spend 45 minutes every Sunday entering receipts into Google Sheets. My partner never remembers to log their purchases."
- **Scenario:** At the grocery store checkout, Sarah photographs the receipt. By the time she's loaded bags into the car, the $127.43 is already logged under "Groceries" and visible to her partner.

### Persona 2: Marcus — The Contributing Partner
- **Age:** 36, works in trades
- **Tech comfort:** Comfortable with phone, dislikes complicated apps
- **Pain:** "Sarah asks me to log expenses but the spreadsheet is confusing on my phone."
- **Scenario:** Marcus buys lunch for $14.50. Opens the app, taps +, types "Lunch" / $14.50, picks "Dining Out", hits save. Done in 8 seconds.

### Persona 3: Jake — The Self-Hosting Admin
- **Age:** 29, software engineer running a home k8s cluster
- **Pain:** "I want a budget app but I don't trust SaaS companies with my financial data."
- **Scenario:** Clones the repo, runs `docker compose up`, logs in via Google OAuth, creates a family, invites partner — all in under 30 minutes.

| Persona | Role | Threat Profile |
|---------|------|----------------|
| **Sarah (Admin)** | Sets up family, defines categories, configures goals | Elevated privileges; compromise grants full data access |
| **Marcus (Member)** | Logs expenses daily, photographs receipts | Primary attack surface is mobile browser session |
| **Casey (Teenager)** | Occasionally logs personal expenses on shared device | Session management must prevent cross-user access |

— *Persona narratives: Worker Charlie. Threat profiles: Worker Bravo.*

---

## 3. Job to Be Done

> **When** I make a purchase while out of the house,
> **I want to** log it to our family budget in under 15 seconds,
> **So that** our household can track spending against monthly goals without needing a computer.

| # | When I... | I want to... | So I can... |
|---|-----------|-------------|-------------|
| 1 | finish paying for something | log the expense in <10 seconds | keep accurate records without breaking my flow |
| 2 | get a paper receipt | photograph it and have data auto-extracted | avoid manual data entry entirely |
| 3 | wonder "how much have we spent on dining?" | open the app and see a progress bar | make an informed decision about tonight's dinner |
| 4 | start a new month | have budgets automatically reset | focus on tracking, not bookkeeping setup |
| 5 | want my partner to participate | invite them to a shared family budget | get complete spending visibility |
| 6 | need data for tax prep | export a month's data to CSV | use familiar tools for deeper analysis |

---

## 4. MVP Scope

### In-Scope

| Feature | Description | Boundary |
|---------|-------------|----------|
| **Expense Entry (Manual)** | 4-field form: date, cost, description, category | Date defaults to today. Cost is positive decimal. Description max 255 chars. Category from user-defined list. |
| **Expense Entry (Receipt Photo)** | Camera capture or upload → Claude extracts date, total, store name → auto-creates entry | One entry per receipt (total amount). No confirmation step. User can edit/delete after. |
| **User-Defined Categories** | CRUD for spending categories per family | Flat (no hierarchy). Categories cannot be hard-deleted if expenses reference them (soft-delete/archive). |
| **Monthly Goals** | Per-category spending limit with progress bar | Green (<80%), yellow (80-99%), red (>=100%). |
| **Automatic Monthly Rollover** | New month begins based on family's configured timezone | Goals copied from previous month on first access. No carryover of unspent amounts. |
| **Families** | Create family, invite existing app users (internal only). Roles: Admin + Member | One family per user. Owner (creator) cannot be demoted. Internal invite system only. |
| **Google Auth** | Google OAuth 2.0 for login | No other auth methods. |
| **CSV Export** | Export monthly budget data as CSV | UTF-8 BOM for Excel. Filterable by category. Summary footer. |

### Out-of-Scope (MVP)

| Feature | Rationale | When |
|---------|-----------|------|
| Intelligent receipt splitting | Complexity of per-item categorization | Post-MVP Phase 1 (immediate next priority) |
| Email/SMS invites to non-users | Brief explicitly excludes | Not planned |
| Bank account sync (Plaid) | Third-party dependency | Future consideration |
| Recurring expense templates | Adds complexity | Post-MVP Phase 2 |
| Multi-currency | Single-household, single-currency | Post-MVP Phase 2 |
| Push notifications | PWA push inconsistent on iOS | Post-MVP Phase 2 |
| Native mobile apps | PWA sufficient for target users | Not planned |

---

## 5. Edge Cases and Error Scenarios

### Receipt Processing

| Scenario | Expected Behavior |
|----------|-------------------|
| Blurry/unreadable receipt | Create expense with `description: "Unreadable receipt"`, `cost: 0`, flag for user edit. Store original photo. |
| Non-receipt image (selfie, screenshot) | Reject: "This doesn't appear to be a receipt. Please try again or enter manually." |
| Receipt in non-English language | Extract numeric amounts; use store name as-is. Claude handles multilingual natively. |
| Handwritten receipt | Best-effort extraction; same as blurry flow if low confidence. |
| Receipt with no date | Default to current date. |
| Receipt with no store name | Set description to "Unknown merchant". |
| Receipt total includes tax | Use the final total (tax-inclusive). |
| Image > 5MB | Reject before upload with client-side validation. |
| Unsupported format | Accept JPEG, PNG, WebP, HEIC. Convert HEIC server-side. Reject others. |

### Timezone

| Scenario | Expected Behavior |
|----------|-------------------|
| Expense at 11:59 PM on March 31 | Attributed to March based on user's local timezone. |
| User changes timezone mid-month | Existing expenses retain original dates. Rollover uses new timezone. |
| Family members in different timezones | Each user has own timezone. Expenses dated by submitter's local date. Monthly rollover uses Admin's timezone. |
| DST transition (spring forward/fall back) | Use IANA timezone database (`zoneinfo`). "Midnight" is always `00:00` wall-clock time. |

### Family Permissions

| Scenario | Expected Behavior |
|----------|-------------------|
| Admin removes themselves | Not allowed. Owner cannot leave. Other admins warned. |
| Last admin tries to demote | Blocked: "Family must have at least one admin." |
| Member edits another member's expense | Allowed. All members can edit/delete any family expense. Only goal-setting and member management are role-restricted. |
| User invited but already in a family | Blocked: "You are already a member of a family." |
| Admin deletes category with expenses | Category is archived (hidden from forms, visible in history). |
| Two admins edit same goal simultaneously | Optimistic concurrency via `version` field. Second save returns 409 Conflict. |

### Concurrent Edits

| Scenario | Expected Behavior |
|----------|-------------------|
| Two users add expenses simultaneously | No conflict — independent rows. Both succeed. |
| Two users edit same expense simultaneously | Optimistic locking via `updated_at`. Second save returns 409 with current state. |
| Edit during CSV export | Export reads consistent snapshot (`REPEATABLE READ`). |

— *Edge cases: Worker Delta.*

---

## 6. User Experience Design

### 6.1 Information Architecture

```
[Login]
  │
  ├── First-time user ──► [Onboarding]
  │                           ├── Create Family
  │                           ├── Add First Categories (suggested defaults)
  │                           └── Set First Goals (optional)
  │
  └── Returning user ──► [Dashboard]
                            ├── [Add Expense] (bottom sheet)
                            │     ├── Manual Entry
                            │     └── Receipt Scan
                            ├── [Budget Detail] (per-category → expense list)
                            ├── [Categories] (CRUD)
                            ├── [Goals] (set/edit monthly limits)
                            ├── [Family] (members, invites, roles)
                            ├── [Export] (CSV download)
                            └── [Settings] (timezone, account, logout)
```

### 6.2 Key User Flows

**Flow 1: Zero to First Expense (Onboarding) — Target: < 5 minutes**
```
Google Sign-In → "Welcome! Let's set up your budget."
  → [Create Family] (single name field)
  → "What do you spend money on?"
    [Suggested: Groceries, Dining, Transport, Entertainment, Bills, Other]
    (tap to select, add custom)
  → "Set monthly goals" (optional — can skip)
  → Dashboard with empty state + prominent FAB
  → User taps FAB → first expense
```

**Design decisions:** No tutorial overlays. Suggested categories reduce blank-page paralysis. Goal-setting is optional — don't block the path to first expense.

**Privacy notice:** During onboarding, users must acknowledge that receipt images are sent to Anthropic's Claude API for processing.

**Flow 2: Add Expense (Manual) — Target: < 10 seconds**
```
Dashboard → Tap FAB (+) → Bottom sheet (not full page)
  Amount: auto-focused, numeric keyboard (inputmode="decimal")
  Description: free text
  Category: dropdown (defaults to most-recently-used)
  Date: defaults to today
  → Save → brief success toast → return to Dashboard
```

**Flow 3: Scan Receipt — Target: < 15 seconds**
```
Dashboard → Tap FAB (+) → Camera icon → Full-screen camera view
  → Capture photo (or pick from gallery)
  → "Reading receipt..." spinner (1-3 sec)
  → Expense auto-created → toast: "Added: $47.23 — Grocery Store → Groceries"
  → Return to Dashboard (progress bars updated)
```

### 6.3 Key Screen Wireframes

**Dashboard:**
```
┌──────────────────────────────────┐
│ ≡  Monthly Budget      [Avatar] │
│──────────────────────────────────│
│  March 2026                      │
│  Total Spent: $1,247 / $2,000   │
│  ████████████████░░░░░░░  62%   │
│                                  │
│ ┌──────────────────────────────┐ │
│ │ Groceries       $423/$600   │ │
│ │ ████████████░░░░░░░░  71%   │ │
│ └──────────────────────────────┘ │
│ ┌──────────────────────────────┐ │
│ │ Dining Out      $189/$200   │ │
│ │ ███████████████████░  95% ⚠ │ │
│ └──────────────────────────────┘ │
│ ┌──────────────────────────────┐ │
│ │ Transport        $67/$150   │ │
│ │ ████████░░░░░░░░░░░░  45%   │ │
│ └──────────────────────────────┘ │
│                          ( + )   │  ← FAB
│──────────────────────────────────│
│  Home  Categories  Family  Settings │
└──────────────────────────────────┘
```

**Add Expense (Bottom Sheet):**
```
┌──────────────────────────────────┐
│  (dimmed dashboard behind)       │
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│
│  Add Expense                     │
│  Amount *    [$          0.00]   │ ← numeric keyboard
│  Description [               ]   │
│  Category    [Groceries    ▼ ]   │ ← defaults to last used
│  Date        [Today (Mar 22)]    │
│  [Camera] [Save]                 │
└──────────────────────────────────┘
```

### 6.4 Mobile-First Design Principles

1. **Thumb-zone optimized:** Primary actions in the bottom 60% of screen
2. **44px minimum touch targets:** All tappable elements (48px preferred)
3. **Single-column layout:** No horizontal scrolling
4. **Bottom navigation:** Home, Categories, Family, Settings. FAB floats above tab bar
5. **Native input types:** `inputmode="decimal"` for amounts, `type="date"` for dates
6. **System fonts:** `font-family: system-ui` for native feel and zero font-loading latency
7. **Offline-aware UI:** Subtle banner "Offline — viewing cached data". Disable receipt scan. Keep manual entry with local queue.

— *UX design, wireframes, and mobile principles: Worker Charlie. Onboarding flow: Worker Charlie.*

---

## 7. Technical Architecture

### 7.1 System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Home Network                             │
│                                                                 │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────┐     │
│  │ Tailscale │───▶│   Caddy      │───▶│   FastAPI Backend  │     │
│  │ (VPN+TLS) │    │ (Reverse     │    │   (Gunicorn+       │     │
│  └──────────┘    │  Proxy)      │    │    Uvicorn workers) │     │
│                  └──────────────┘    └─────────┬──────────┘     │
│                                                │                │
│                         ┌──────────────────────┼──────────┐     │
│                         │                      │          │     │
│                         ▼                      ▼          ▼     │
│                  ┌─────────────┐    ┌────────────┐ ┌──────────┐ │
│                  │ PostgreSQL  │    │   Redis     │ │ Receipt  │ │
│                  │ (encrypted  │    │ (sessions + │ │ Storage  │ │
│                  │  at rest)   │    │  rate limit)│ │ (volume) │ │
│                  └─────────────┘    └────────────┘ └──────────┘ │
│                                                                 │
│                  ┌─────────────────────────────┐                │
│                  │  Anthropic API (external)    │                │
│                  │  Claude receipt parsing      │                │
│                  └─────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Component Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Frontend | React 18+ with Vite + TypeScript | Lightweight PWA, fast builds, no SSR attack surface |
| UI Components | Chakra UI | Mobile-first by default, accessible, lightweight |
| PWA | vite-plugin-pwa + Workbox | Service worker generation, precaching, offline support |
| State Management | React Query (TanStack Query) | Server-state caching, auto-refetch, optimistic updates |
| Reverse Proxy | Caddy 2.x | Auto TLS via Tailscale, security headers, rate limiting at edge |
| Backend | Python 3.12+ FastAPI + Gunicorn | Async-native, type-safe, built-in OpenAPI validation |
| ORM | SQLAlchemy 2.0 (async) + Alembic | Mature async support via asyncpg, standard migrations |
| Database | PostgreSQL 16 | Row-level security, pgcrypto, native SSL, ACID for financial data |
| Cache/Rate Limit | Redis 7 (Alpine) | Session store, rate limit counters, ephemeral data only |
| AI/OCR | Anthropic Claude API (claude-haiku-4-5-20251001) | Receipt parsing at ~$0.0015/receipt. Structured output via tool use |
| Auth | Google OAuth 2.0 + JWT (PyJWT + Authlib) | No password storage; Google handles credential security |
| TLS | Tailscale + Caddy | Zero-config HTTPS with automatic cert renewal |
| Containers | Docker Compose (dev), Kubernetes (prod) | Pod security standards, network policies |

— *Architecture: Worker Bravo (security-first). Tech choices enriched from Workers Alpha and Charlie.*

---

## 8. Security and Threat Model

### 8.1 STRIDE Threat Analysis

| # | Threat | STRIDE | Attack Vector | Impact | Mitigation |
|---|--------|--------|---------------|--------|------------|
| T1 | Attacker forges JWT | Spoofing | Stolen/weak signing key | Account takeover | HMAC-SHA256 with 256-bit random secret rotated quarterly; 15-min access tokens; refresh tokens bound to device |
| T2 | Member escalates to Admin | Tampering | Modify role in JWT or API | Unauthorized management | Role stored server-side in DB, never in JWT; checked every request via DB lookup |
| T3 | User views another family's expenses | Info Disclosure | IDOR on `/api/expenses/{id}` | Financial data leak | PostgreSQL RLS enforces family-scoped access; API validates `family_id` ownership |
| T4 | Attacker denies creating an expense | Repudiation | No audit trail | Incorrect budget | Immutable audit log with `created_by`, `created_at`, `ip_address`; soft-delete only |
| T5 | Malicious receipt exploits parser | Tampering | Polyglot file (image + script) | RCE on backend | Magic-byte validation, Pillow re-encoding, 5MB limit, dedicated upload volume |
| T6 | Anthropic API key leaked | Info Disclosure | Docker history, env dump, logs | Billing fraud | K8s Secrets as files (not env vars); log sanitization; `.dockerignore` excludes secrets |
| T7 | OAuth token replay | Spoofing | Replay stolen auth code | Account takeover | PKCE (S256); single-use auth codes; state parameter validated |
| T8 | DDoS on self-hosted instance | DoS | Volumetric attack on home IP | Service down | Tailscale restricts to VPN; Caddy rate limiting; Redis sliding-window limiter |
| T9 | SQL injection via description | Tampering | Malicious text input | Data exfiltration | SQLAlchemy ORM with parameterized queries; Pydantic validation with max-length |
| T10 | Cross-family leak via CSV export | Info Disclosure | Manipulated `family_id` | Bulk data theft | RLS on query; server-side membership check; CSV from RLS-filtered query only |
| T11 | Session hijacking on shared device | Spoofing | Stolen session cookie | Impersonation | HttpOnly + Secure + SameSite=Strict; 24h session expiry; explicit logout |
| T12 | K8s API privilege escalation | Elevation | Compromised pod | Cluster takeover | Restricted PSS; minimal RBAC; no automount service account token; NetworkPolicy blocks k8s API |

### 8.2 Attack Surface Map

```
External Entry Points:
  ├── HTTPS endpoint (Caddy) ← only via Tailscale VPN
  │     ├── /api/auth/* (Google OAuth flow)
  │     ├── /api/expenses/* (CRUD, file upload)
  │     ├── /api/categories/* (CRUD)
  │     ├── /api/goals/* (CRUD)
  │     ├── /api/families/* (management, invites)
  │     ├── /api/export/* (CSV download)
  │     └── /static/* (React PWA assets)
  └── Anthropic API (outbound HTTPS only)

Internal:
  ├── PostgreSQL (TCP 5432, internal only)
  ├── Redis (TCP 6379, internal only, AUTH required)
  ├── Receipt volume (read-write by API only)
  └── K8s API (blocked by NetworkPolicy)
```

— *STRIDE analysis and attack surface: Worker Bravo.*

---

## 9. Authentication and Authorization

### 9.1 Google OAuth 2.0 Flow (with PKCE)

```
User            React PWA          FastAPI           Google
 │                 │                  │                 │
 │─ Click Login ──▶│                  │                 │
 │                 │── Generate PKCE ─┐                 │
 │                 │   code_verifier  │                 │
 │                 │   code_challenge │                 │
 │                 │── Redirect ──────┼────────────────▶│
 │                 │   client_id      │                 │
 │                 │   code_challenge │                 │
 │                 │   state (CSRF)   │                 │
 │                 │   scope=email+profile              │
 │◀── Google Consent ──────────────────────────────────│
 │── Approve ─────▶│                  │                 │
 │                 │◀─ Callback ──────┼─────────────────│
 │                 │── POST /api/auth/callback ────────▶│
 │                 │   auth_code + code_verifier        │
 │                 │                  │── Token Exchange─▶│
 │                 │                  │◀── id_token ─────│
 │                 │                  │── Verify sig, iss, aud, exp
 │                 │◀── Set cookies ──│                  │
 │                 │   access_token (HttpOnly, Secure,  │
 │                 │     SameSite=Strict, 15min)        │
 │                 │   refresh_token (HttpOnly, Secure, │
 │                 │     SameSite=Strict, 7 days)       │
```

### 9.2 JWT Design

**Critical:** Roles (Admin/Member) are **never** stored in JWT. They are always looked up from the database on each request. This prevents role tampering.

```python
# Access token payload (15 minutes)
{
    "sub": "google-oauth-sub-id",
    "user_id": "uuid-internal",
    "iat": 1711100000,
    "exp": 1711100900,
    "jti": "unique-token-id"
}
```

### 9.3 RBAC Permission Matrix

```
                          Admin    Member
─────────────────────────────────────────
Create expense              ✓        ✓
View family expenses        ✓        ✓
Edit any expense            ✓        ✓
Delete any expense          ✓        ✓
Create/edit categories      ✓        ✗
Set monthly goals           ✓        ✗
Invite members              ✓        ✗
Remove members              ✓        ✗
Export CSV                  ✓        ✓
Leave family                ✓*       ✓

* Owner (creator) cannot leave; must transfer or delete family
```

— *Auth design and RBAC: Worker Bravo. JWT anti-pattern fix: Worker Delta insight.*

---

## 10. Database Schema

```sql
-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For category suggestion

-- USERS
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_id       VARCHAR(255) NOT NULL UNIQUE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    display_name    VARCHAR(255) NOT NULL,
    avatar_url      TEXT,
    timezone        VARCHAR(64) NOT NULL DEFAULT 'America/New_York',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FAMILIES
CREATE TABLE families (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    timezone        VARCHAR(64) NOT NULL DEFAULT 'America/New_York',
    edit_grace_days INTEGER NOT NULL DEFAULT 7,
    created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- FAMILY MEMBERS (join table with role)
CREATE TABLE family_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id       UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(20) NOT NULL DEFAULT 'member'
                    CHECK (role IN ('admin', 'member')),
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (family_id, user_id)
);

-- INVITES
CREATE TABLE invites (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id       UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    invited_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    invited_by      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'accepted', 'declined')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    responded_at    TIMESTAMPTZ,
    UNIQUE (family_id, invited_user_id, status)
);

-- CATEGORIES (per-family)
CREATE TABLE categories (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id       UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    icon            VARCHAR(50),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (family_id, name)
);

-- MONTHLY GOALS (per-family, per-category, per-month)
CREATE TABLE monthly_goals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id       UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    category_id     UUID NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    year_month      VARCHAR(7) NOT NULL,  -- 'YYYY-MM'
    amount_cents    INTEGER NOT NULL CHECK (amount_cents > 0),
    version         INTEGER NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (family_id, category_id, year_month)
);

-- RECEIPTS (decoupled from expenses for async processing)
CREATE TABLE receipts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id       UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    uploaded_by     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    image_path      TEXT NOT NULL,
    raw_response    JSONB,  -- Full Claude API response for debugging
    parsed_date     DATE,
    parsed_total_cents INTEGER,
    parsed_merchant VARCHAR(255),
    status          VARCHAR(20) NOT NULL DEFAULT 'processing'
                    CHECK (status IN ('processing', 'completed', 'failed')),
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- EXPENSES
CREATE TABLE expenses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id       UUID NOT NULL REFERENCES families(id) ON DELETE CASCADE,
    category_id     UUID NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    amount_cents    INTEGER NOT NULL CHECK (amount_cents > 0),
    description     VARCHAR(500) NOT NULL DEFAULT '',
    expense_date    DATE NOT NULL,
    year_month      VARCHAR(7) NOT NULL,  -- denormalized for fast monthly queries
    receipt_id      UUID REFERENCES receipts(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- REFRESH TOKEN BLACKLIST
CREATE TABLE refresh_token_blacklist (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jti             VARCHAR(255) NOT NULL UNIQUE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- AUDIT LOG (immutable)
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id         UUID REFERENCES users(id),
    family_id       UUID REFERENCES families(id),
    action          VARCHAR(50) NOT NULL,
    resource_type   VARCHAR(50) NOT NULL,
    resource_id     UUID,
    details         JSONB,
    ip_address      INET NOT NULL,
    user_agent      TEXT,
    success         BOOLEAN NOT NULL DEFAULT true
);

-- Revoke UPDATE/DELETE on audit_log for app role
REVOKE UPDATE, DELETE ON audit_log FROM app_user;

-- INDEXES
CREATE INDEX idx_expenses_family_month ON expenses(family_id, year_month);
CREATE INDEX idx_expenses_family_category_month ON expenses(family_id, category_id, year_month);
CREATE INDEX idx_expenses_user ON expenses(user_id);
CREATE INDEX idx_expenses_date ON expenses(expense_date);
CREATE INDEX idx_monthly_goals_family_month ON monthly_goals(family_id, year_month);
CREATE INDEX idx_family_members_family ON family_members(family_id);
CREATE INDEX idx_family_members_user ON family_members(user_id);
CREATE INDEX idx_invites_invited_user ON invites(invited_user_id, status);
CREATE INDEX idx_receipts_family ON receipts(family_id);
CREATE INDEX idx_receipts_status ON receipts(status);
CREATE INDEX idx_blacklist_jti ON refresh_token_blacklist(jti);
CREATE INDEX idx_blacklist_expires ON refresh_token_blacklist(expires_at);
CREATE INDEX idx_audit_log_family_time ON audit_log(family_id, timestamp DESC);
CREATE INDEX idx_categories_family ON categories(family_id);
CREATE INDEX idx_expenses_description_trgm ON expenses USING gin (description gin_trgm_ops);
```

### Schema Design Decisions

| Decision | Rationale |
|----------|-----------|
| `amount_cents INTEGER` | Avoids floating-point display issues. All math is integer arithmetic. Frontend divides by 100. |
| `year_month VARCHAR(7)` denormalized | Eliminates `DATE_TRUNC` in every dashboard query. Simple string comparison for monthly queries. |
| UUIDs for all PKs | No sequential ID leakage. Safe for client-side references. |
| `receipts` as separate table | Decouples receipt processing from expense creation. Enables async retry on failure. Preserves raw Claude response. |
| `family_id` on every data table | A family *is* the tenant. No separate multi-tenancy table needed. |
| `pg_trgm` index on descriptions | Powers category suggestion via trigram similarity matching on merchant names. |
| `edit_grace_days` on families | Configurable window (default 7 days) for editing past-month expenses. |

— *Integer-cents and separate receipts table: Worker Alpha. Audit log and schema structure: Worker Bravo. Grace period and version field: Worker Delta.*

---

## 11. Row-Level Security

```sql
-- Enable and force RLS
ALTER TABLE expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE expenses FORCE ROW LEVEL SECURITY;
ALTER TABLE categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE categories FORCE ROW LEVEL SECURITY;
ALTER TABLE monthly_goals ENABLE ROW LEVEL SECURITY;
ALTER TABLE monthly_goals FORCE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- Helper: check family membership
CREATE OR REPLACE FUNCTION user_in_family(check_family_id UUID) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM family_members
        WHERE user_id = current_setting('app.current_user_id')::UUID
        AND family_id = check_family_id
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

-- Helper: check admin role
CREATE OR REPLACE FUNCTION user_is_family_admin(check_family_id UUID) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM family_members
        WHERE user_id = current_setting('app.current_user_id')::UUID
        AND family_id = check_family_id
        AND role = 'admin'
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER STABLE;

-- Expenses: members read all family expenses, write own
CREATE POLICY expenses_select ON expenses FOR SELECT
    USING (user_in_family(family_id));

CREATE POLICY expenses_insert ON expenses FOR INSERT
    WITH CHECK (user_in_family(family_id)
        AND user_id = current_setting('app.current_user_id')::UUID);

CREATE POLICY expenses_update ON expenses FOR UPDATE
    USING (user_in_family(family_id));

-- Categories: all members read, admin writes
CREATE POLICY categories_select ON categories FOR SELECT
    USING (user_in_family(family_id));

CREATE POLICY categories_write ON categories FOR INSERT
    WITH CHECK (user_is_family_admin(family_id));

-- Goals: all members read, admin writes
CREATE POLICY goals_select ON monthly_goals FOR SELECT
    USING (user_in_family(family_id));

CREATE POLICY goals_write ON monthly_goals FOR INSERT
    WITH CHECK (user_is_family_admin(family_id));

-- Audit log: read-only for family members
CREATE POLICY audit_select ON audit_log FOR SELECT
    USING (user_in_family(family_id));
```

— *RLS policies: Worker Bravo.*

---

## 12. API Surface

Base URL: `/api/v1`. All endpoints require JWT unless noted. Amounts in **cents** (integer).

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/auth/google/login` | None | Redirect to Google OAuth |
| GET | `/auth/google/callback` | None | OAuth callback, sets cookies |
| POST | `/auth/refresh` | Cookie | Refresh access token |
| POST | `/auth/logout` | JWT | Blacklist refresh token, clear cookies |
| GET | `/me` | JWT | Current user profile + family memberships |
| PUT | `/me` | JWT | Update display_name, timezone |

### Families

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/families` | JWT | Create family (creator = Admin) |
| GET | `/families/{id}` | JWT | Family details + members |
| POST | `/families/{id}/invites` | Admin | Invite existing user by email |
| GET | `/invites` | JWT | List pending invites for current user |
| POST | `/invites/{id}/respond` | JWT | Accept or decline invite |
| DELETE | `/families/{id}/members/{uid}` | Admin | Remove member |
| PATCH | `/families/{id}/members/{uid}` | Admin | Change role |

#### Example: Create Family
```json
// POST /api/v1/families
// Request:
{ "name": "Smith Household", "timezone": "America/Chicago" }

// Response 201:
{
  "id": "uuid",
  "name": "Smith Household",
  "timezone": "America/Chicago",
  "created_at": "2026-03-22T10:00:00Z"
}
```

### Expenses

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/families/{id}/expenses?year_month=YYYY-MM&category_id=UUID&page=1&per_page=50` | Member | List expenses (paginated) |
| POST | `/families/{id}/expenses` | Member | Create manual expense |
| POST | `/families/{id}/receipts` | Member | Upload receipt (multipart) |
| PUT | `/families/{id}/expenses/{eid}` | Member | Edit expense |
| DELETE | `/families/{id}/expenses/{eid}` | Member | Delete expense |

#### Example: Create Expense
```json
// POST /api/v1/families/{id}/expenses
// Request:
{
  "amount_cents": 4523,
  "description": "Whole Foods Market",
  "category_id": "uuid",
  "expense_date": "2026-03-21"
}

// Response 201:
{
  "id": "uuid",
  "amount_cents": 4523,
  "description": "Whole Foods Market",
  "category": { "id": "uuid", "name": "Groceries" },
  "user": { "id": "uuid", "display_name": "Jordan Smith" },
  "expense_date": "2026-03-21",
  "receipt_id": null,
  "created_at": "2026-03-21T18:30:00Z"
}
```

### Budget Dashboard

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/families/{id}/budget/summary?month=YYYY-MM` | Member | Per-category: goal, spent, remaining, percentage, status |

### Categories & Goals

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/families/{id}/categories` | Member | List active categories |
| POST | `/families/{id}/categories` | Admin | Create category |
| PUT | `/families/{id}/categories/{cid}` | Admin | Update category |
| DELETE | `/families/{id}/categories/{cid}` | Admin | Archive category |
| GET | `/families/{id}/goals?month=YYYY-MM` | Member | Goals for month (copies from previous if none) |
| PUT | `/families/{id}/goals` | Admin | Set/update goals |

### Export

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/families/{id}/export?month=YYYY-MM&category_id=UUID` | Member | Download CSV |

### Error Response Format

```json
{
  "error": {
    "code": "CATEGORY_HAS_EXPENSES",
    "message": "Cannot delete category with existing expenses. Archived instead.",
    "details": { "category_id": "uuid", "expense_count": 12 }
  }
}
```

### Rate Limiting

| Endpoint Group | Limit | Window | Key |
|---------------|-------|--------|-----|
| `POST /api/auth/*` | 10 req | per minute | IP |
| `POST /api/*/receipts` | 10 req | per minute | User ID (costly Claude calls) |
| `GET /api/*/export/*` | 5 req | per hour | User ID |
| All other authenticated | 120 req | per minute | User ID |

— *API structure: Worker Bravo. JSON examples: Worker Alpha. Budget summary endpoint: Worker Delta. Rate limits: Worker Bravo.*

---

## 13. Receipt Processing Pipeline

### Flow

```
User taps "Scan Receipt"
        |
        v
[Camera/Gallery] (Frontend)
        | Client validation: JPEG/PNG/WebP/HEIC, ≤5MB, ≥200x200px
        v
[Upload to POST /api/families/{id}/receipts]
        |
        v
[FastAPI Endpoint]
        | 1. Magic-byte validation (python-magic)
        | 2. Pillow re-encoding (strips embedded payloads)
        | 3. Save with UUID filename to /data/receipts/{family_id}/
        | 4. Create receipt record (status: 'processing')
        | 5. Convert HEIC → JPEG if needed
        | 6. Resize if > 4MP to reduce API cost
        v
[Call Claude API]
        | Model: claude-haiku-4-5-20251001
        | Method: Tool use (structured output)
        v
[Parse Response]
        |── Success ──────────→ Create expense, mark receipt 'completed', return 201
        |── Partial (no date) → Fill defaults (date=today), create expense, return 201
        |── Not a receipt ────→ Return 422: "Not a receipt"
        |── Low confidence ───→ Create with amount=0 + "please edit" flag, return 201
        |── API error ────────→ Return 503: "Try again or enter manually" (image saved)
```

### Claude API Call

```python
response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    system="You are a receipt data extractor. Extract the total amount, date, "
           "and store name from the receipt image.",
    tools=[{
        "name": "extract_receipt",
        "description": "Extract structured data from a receipt image",
        "input_schema": {
            "type": "object",
            "properties": {
                "is_receipt": {"type": "boolean"},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "total_amount": {"type": "number"},
                "date": {"type": "string", "description": "YYYY-MM-DD or null"},
                "store_name": {"type": "string", "description": "Merchant name or null"}
            },
            "required": ["is_receipt", "confidence"]
        }
    }],
    tool_choice={"type": "tool", "name": "extract_receipt"},
    messages=[{
        "role": "user",
        "content": [{"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg", "data": base64_data
        }}]
    }]
)
```

### Category Suggestion (pg_trgm)

After Claude extracts the store name:
1. Query previous expenses with similar `description` (trigram similarity > 0.6)
2. If match found, use that expense's category
3. If no match, use the family's most-used category as default
4. User can change after the fact

### Cost Estimation

- **claude-haiku-4-5-20251001:** ~$0.80/M input, ~$4/M output tokens
- **Average receipt:** ~1,100 input tokens + ~150 output = **~$0.0015/receipt**
- **Family of 4, 60 receipts/month:** **~$0.09/month**

— *Receipt pipeline: Worker Delta. Image security pipeline: Worker Bravo. Tool use approach: Worker Delta.*

---

## 14. Monthly Rollover Logic

There is no cron job. Months are implicit, driven by the current date in the family's timezone.

```python
from zoneinfo import ZoneInfo
from datetime import datetime

def get_current_budget_month(family_timezone: str) -> str:
    """Returns 'YYYY-MM' for the current month in the family's timezone."""
    now = datetime.now(ZoneInfo(family_timezone))
    return now.strftime("%Y-%m")

def get_goals_for_month(family_id, month):
    """Lazy-copy: if no goals exist for this month, copy from previous."""
    goals = db.query(Goal).filter(family_id=family_id, year_month=month).all()
    if not goals:
        latest = db.query(Goal).filter(
            family_id=family_id, year_month < month
        ).order_by(year_month.desc()).first()
        if latest:
            # Copy all goals from that month
            for g in db.query(Goal).filter(family_id=family_id, year_month=latest.year_month):
                db.add(Goal(family_id=family_id, category_id=g.category_id,
                            amount_cents=g.amount_cents, year_month=month))
            db.commit()
            return get_goals_for_month(family_id, month)
    return goals
```

### Grace Period

- Past-month expenses can be added/edited for `edit_grace_days` (default 7) after month ends
- After grace period, past-month expenses are read-only
- Prevents "I forgot to log yesterday's receipt" frustration without permanently reopening old months

— *Rollover logic: Workers Alpha and Delta. Grace period: Worker Delta.*

---

## 15. CSV Export Specification

- **Encoding:** UTF-8 with BOM (`\xEF\xBB\xBF`) for Excel compatibility
- **Delimiter:** Comma. **Line ending:** CRLF
- **Filename:** `monthly-budget_{family_name}_{YYYY-MM}.csv`

| Column | Type | Example |
|--------|------|---------|
| Date | YYYY-MM-DD | 2026-03-15 |
| Amount | Decimal (2 places) | 42.99 |
| Description | String | "Walmart - Groceries" |
| Category | String | "Groceries" |
| Added By | String | "Jane Smith" |
| Entry Method | "Manual" or "Receipt" | "Receipt" |
| Created At | ISO 8601 | 2026-03-15T14:23:00-05:00 |

### Summary Footer

```csv
,,,,,,
,SUMMARY,,,,,
,Total Expenses:,523.47,,,,
,Number of Entries:,34,,,,
,Date Range:,2026-03-01 to 2026-03-31,,,,
```

— *CSV specification: Worker Delta.*

---

## 16. Secret Management

| Secret | Dev Storage | Prod Storage | Rotation |
|--------|-------------|--------------|----------|
| JWT signing key | `.env` (gitignored) | K8s Secret, file mount | Quarterly |
| Google OAuth client ID | `.env` | K8s Secret, env var | On compromise |
| Google OAuth client secret | `.env` | K8s Secret, file mount | Annually |
| Anthropic API key | `.env` | K8s Secret, file mount | Annually |
| PostgreSQL password | `.env` | K8s Secret, env var | Quarterly |
| Redis AUTH password | `.env` | K8s Secret, env var | Quarterly |

### Rules
1. Never embed secrets in Docker images
2. Never log secrets — sanitization middleware strips patterns
3. Never pass as CLI arguments
4. `.env` in `.gitignore` and `.dockerignore`
5. K8s Secrets mounted as files use `defaultMode: 0400`
6. Pre-commit hook runs `detect-secrets`

```python
def load_secret(env_var: str, file_path: str | None = None) -> str:
    value = os.getenv(env_var)
    if value:
        return value
    if file_path and Path(file_path).exists():
        return Path(file_path).read_text().strip()
    raise RuntimeError(f"Secret {env_var} not configured")
```

— *Secret management: Worker Bravo.*

---

## 17. Container Security

### Dockerfile (Multi-stage, Non-root)

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libmagic1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup src/ .
RUN mkdir -p /tmp/app && chown appuser:appgroup /tmp/app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
ENTRYPOINT ["gunicorn", "main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", \
            "--bind", "0.0.0.0:8000"]
```

### Docker Compose (Hardened Development)

```yaml
services:
  api:
    build: .
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=100m
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '1.0'
    volumes:
      - receipt_data:/data/receipts
    secrets:
      - anthropic_api_key
      - jwt_secret
      - google_client_secret

  postgres:
    image: postgres:16-alpine
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid
      - /run/postgresql
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - CHOWN
      - SETUID
      - SETGID
      - FOWNER
      - DAC_READ_SEARCH
    volumes:
      - pg_data:/var/lib/postgresql/data
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password

  redis:
    image: redis:7-alpine
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    command: redis-server --requirepass "${REDIS_PASSWORD}" --maxmemory 128mb

secrets:
  anthropic_api_key:
    file: ./secrets/anthropic_api_key.txt
  jwt_secret:
    file: ./secrets/jwt_secret.txt
  google_client_secret:
    file: ./secrets/google_client_secret.txt
  db_password:
    file: ./secrets/db_password.txt

volumes:
  pg_data:
  receipt_data:
```

— *Container security: Worker Bravo.*

---

## 18. Developer Experience

### Local Setup

```bash
# Prerequisites: Docker, Docker Compose, Node.js 20+, Python 3.12+
git clone <repo> && cd monthly-budget

# One-command full stack:
docker compose up

# Or manual (with hot reload):
docker compose up -d db redis
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && cp .env.example .env
alembic upgrade head && uvicorn app.main:app --reload --port 8000
# Separate terminal:
cd frontend && npm install && cp .env.example .env.local && npm run dev
```

### Project Structure

```
monthly-budget/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py           # Pydantic BaseSettings
│   │   ├── database.py         # Async engine, session factory
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic request/response
│   │   ├── services/           # Business logic
│   │   └── routers/            # API route handlers
│   ├── alembic/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/              # useCamera, useOffline, useBudget
│   │   ├── api/                # Fetch wrappers
│   │   └── App.tsx
│   ├── public/manifest.json
│   ├── vite.config.ts
│   └── Dockerfile
├── k8s/                        # Kubernetes manifests
├── docker-compose.yml
└── docker-compose.prod.yml
```

### Conventions

- **Formatting:** Backend: `ruff`. Frontend: `prettier` + `eslint`
- **Type safety:** Python type hints + Pydantic. TypeScript strict mode
- **Migrations:** Alembic auto-generate. One migration per feature branch
- **API docs:** Auto-generated OpenAPI at `/docs`
- **Git:** Feature branches off `main`. Squash merge. Conventional commits

— *Project structure: Worker Alpha. DX conventions: Worker Charlie.*

---

## 19. Testing Strategy

### Testing Pyramid

| Layer | Tool | Target Coverage |
|-------|------|-----------------|
| Unit | pytest (backend), Vitest (frontend) | 80%+ business logic |
| Integration | pytest + httpx (AsyncClient) against real PostgreSQL | All endpoints, happy + error paths |
| E2E | Playwright | 5 critical user flows |

### Key Acceptance Criteria

**Expense Entry:** User creates expense in <3 taps. Amount stored as cents. Appears immediately for all family members. Budget progress updates in same request.

**Receipt Upload:** JPEG/PNG ≤5MB accepted. Successful parse auto-creates expense. Parse failure shows clear error with manual entry fallback. Processing < 5 seconds (p95).

**Monthly Rollover:** New month auto-copies previous goals. Rollover respects family timezone. Grace period (7 days) for past-month edits.

**Families:** Admin can invite by email (existing users only). Non-admin cannot invite/remove/set goals. Owner cannot be removed.

**CSV Export:** Opens correctly in Excel/Sheets/Numbers. UTF-8 BOM present. Summary footer with totals.

### E2E Critical Flows

1. New user signup → create family → add category → set goal → add expense → verify dashboard
2. Receipt photo upload → auto-expense creation → verify amount on dashboard
3. Admin invites member → member accepts → member adds expense → admin sees it
4. Month rollover: set March goals → April → verify goals copied
5. CSV export → verify file downloads with correct data

---

## 20. Observability and Monitoring

### Metrics (Prometheus-compatible)

| Metric | Type | Labels |
|--------|------|--------|
| `http_requests_total` | Counter | method, path, status |
| `http_request_duration_seconds` | Histogram | method, path |
| `receipt_processing_duration_seconds` | Histogram | confidence, success |
| `receipt_processing_total` | Counter | result (success, partial, not_receipt, error) |
| `claude_api_tokens_total` | Counter | direction (input, output) |
| `active_families` | Gauge | — |
| `expenses_created_total` | Counter | source (manual, receipt) |

### Health Checks

- `GET /api/health` — API running + DB reachable
- `GET /api/health/ready` — Ready for traffic (migrations current)

### Alerting Thresholds

| Condition | Alert |
|-----------|-------|
| API p95 > 2s for 5 min | Warning |
| Receipt p95 > 10s for 5 min | Warning |
| Claude API error rate > 20% for 10 min | Critical |
| DB connection pool > 80% | Warning |
| Disk usage > 85% (receipt storage) | Warning |

— *Metrics: Worker Alpha. Alerting: Worker Alpha.*

---

## 21. Audit Logging

### Events Logged

| Event | Severity | Details |
|-------|----------|---------|
| `auth.login` | INFO | Google sub ID, IP, user agent |
| `auth.logout` | INFO | Session duration |
| `auth.failed` | WARN | Reason, IP |
| `expense.create` | INFO | Amount, category, method |
| `expense.update` | INFO | Old/new values |
| `expense.delete` | INFO | Soft-delete, snapshot |
| `receipt.upload` | INFO | File size, extracted data |
| `receipt.parse_error` | WARN | Claude error details |
| `member.invite` | INFO | Inviter, invitee |
| `member.remove` | WARN | Removed by, removed user |
| `export.download` | INFO | Month, row count |

### Incident Response

| Scenario | Detection | Response |
|----------|-----------|----------|
| Account compromise | Multiple `auth.failed` from unknown IPs | Revoke refresh tokens; notify via app banner |
| API key leak | GitHub secret scanning; unexpected usage | Rotate immediately; update K8s Secret; restart pods |
| Rate limit abuse | Sustained `rate_limit.exceeded` | Block IP at Caddy; review for DDoS |

— *Audit logging and incident response: Worker Bravo.*

---

## 22. Roadmap and Phasing

### Phase 1: MVP (Weeks 1-8)

| Week | Focus |
|------|-------|
| 1-2 | Project setup, DB schema, Google OAuth, Docker Compose |
| 3-4 | Expense CRUD (manual), categories, monthly goals, dashboard |
| 5-6 | Receipt upload + Claude integration, PWA setup, family management |
| 7-8 | CSV export, testing, deployment to k8s, polish |

### Phase 2: Intelligent Receipt Splitting (Weeks 9-11)

- Claude analyzes receipt line items and maps to user categories
- e.g., grocery receipt with beer → "Alcohol", cleaning supplies → "Home", food → "Groceries"
- Uses expanded Claude prompt with category list context

### Phase 3: Polish & Growth (Weeks 12+)

- Recurring expense templates
- Historical trend charts
- Budget rollover (carry unspent amounts)
- Sub-categories
- Multi-currency support

---

## 23. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Time to first expense (onboarding) | < 5 minutes | Timestamp: account creation → first expense |
| Manual expense entry time | < 10 seconds | Frontend timing from FAB tap to save |
| Receipt scan success rate | > 85% | `receipt_processing_total{result=success}` / total |
| Receipt processing latency (p95) | < 5 seconds | `receipt_processing_duration_seconds` |
| Weekly active users / total users | > 60% | DAU/WAU tracking |
| Expenses per user per week | > 5 | Leading indicator: users logging 5+/week in first week are likely retained |
| Monthly API cost | < $1 | Claude API billing |

---

## 24. Competitive Differentiation

| Dimension | Monthly Budget | YNAB | Actual Budget | Firefly III |
|-----------|---------------|------|---------------|-------------|
| Price | Free (self-hosted) | $109/yr | Free | Free |
| Receipt scanning | AI-powered (Claude) | No | No | No |
| Mobile UX | PWA, mobile-first | Native apps | Desktop-first | Responsive desktop |
| Family collaboration | Shared goals + roles | Multi-user | Sync only | Multi-user, no roles |
| Data sovereignty | Self-hosted | Cloud | Local/sync | Self-hosted |
| Setup time | < 30 minutes | Instant (SaaS) | Moderate | Complex |

— *Competitive differentiation: Worker Delta.*

---

## 25. Risks and Open Questions

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude API accuracy on receipts | Poor UX if extraction fails often | claude-haiku-4-5-20251001 + structured output. Fallback to manual. Track success rate. |
| Anthropic API pricing changes | Budget impact for heavy users | Haiku is already cheapest tier. $0.09/month for typical family. Monitor. |
| PWA camera quality on iOS | Inconsistent UX | Test extensively on iOS Safari. Gallery picker as fallback. |
| Home k8s reliability | Data loss risk | PostgreSQL PVC with backup strategy. Daily pg_dump to external storage. |
| Google OAuth dependency | Login failure if Google is down | Short-lived but reasonable — JWTs work offline for 15 min. |
| Single-family-per-user constraint | Users wanting multiple budgets | Design decision for simplicity. Revisit post-MVP based on feedback. |

### Open Questions (with Recommendations)

| Question | Recommendation | Decision Needed By |
|----------|---------------|-------------------|
| FastAPI vs Django? | FastAPI — async-native, lighter, better for API-only backend | Before Phase 1, Week 1 |
| Receipt image retention policy? | 90 days, configurable per family | Before Phase 1, Week 5 |
| Family size limit? | 10 members max (configurable) | Before Phase 1, Week 5 |
| Offline expense queue? | MVP: view cached data only. Post-MVP: offline write queue | Post-MVP |

— *Risks and open questions: Worker Delta.*

---

## 26. Glossary

| Term | Definition |
|------|-----------|
| **Admin** | Family member with elevated permissions (manage members, set goals, manage categories) |
| **Member** | Family member who can add expenses and view the budget |
| **Owner** | The Admin who created the family; cannot be demoted or removed |
| **Family** | A household group sharing a single budget. One family per user. |
| **Category** | User-defined spending bucket (e.g., "Groceries", "Dining Out") |
| **Monthly Goal** | A spending limit set per category per month |
| **Rollover** | Automatic transition to a new month's budget, with goals copied from previous month |
| **Grace Period** | Configurable window (default 7 days) after month end during which past-month expenses can still be edited |
| **Receipt Scan** | Uploading a photo of a receipt for AI-powered data extraction |
| **PWA** | Progressive Web App — web application that can be installed to the home screen and works offline |
| **RLS** | Row-Level Security — PostgreSQL feature enforcing data isolation at the database level |
| **STRIDE** | Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege |

---

## Provenance

This PRD was synthesized from 4 competing drafts via the PRD Arena process:

| Section | Primary Source | Enriched From |
|---------|---------------|---------------|
| Problem Statement & Competitive Landscape | Workers Delta + Bravo | — |
| Personas & UX Design | Worker Charlie | Worker Bravo (threat profiles) |
| Edge Cases | Worker Delta | — |
| Technical Architecture | Worker Bravo | Worker Alpha (component stack) |
| Security & Threat Model (STRIDE) | Worker Bravo | — |
| Authentication & Authorization | Worker Bravo | Worker Delta (JWT anti-pattern) |
| Database Schema | Worker Alpha (integer-cents, receipts table) | Workers Bravo (RLS) + Delta (grace period, version) |
| API Surface | Worker Alpha (JSON examples) | Workers Bravo (rate limits) + Delta (budget/summary) |
| Receipt Processing | Worker Delta (flow, cost model) | Worker Bravo (image security pipeline) |
| Container Security | Worker Bravo | — |
| CSV Export | Worker Delta | — |
| Developer Experience | Worker Alpha (project structure) | Worker Charlie (conventions) |
| Observability | Worker Alpha | — |
| Roadmap & Success Metrics | Worker Delta | — |
