# Services — AGENTS.md

Business logic. Services take a `UnitOfWork` (or the single repository they need) plus plain
arguments, raise `HTTPException` or domain errors, and never commit (except `receipt_service`;
see [ports/AGENTS.md](../ports/AGENTS.md)). Pure math lives in `services/assets/` with no I/O.

## Map

| Module | Does |
|---|---|
| `category_service`, `expense_service`, `family_service`, `monthly_goal_service`, `recurring_service`, `user_service`, `asset_service` (+ `asset_links`, `asset_analytics`, `assets/`) | CRUD + rules per aggregate |
| `receipt_service` | Three-phase upload: validate/sanitize image (`receipt_storage`), extract (`claude_client`), create Expense with a category from `category_suggestion`. Images are never persisted |
| `claude_client` | Receipt extraction via OpenRouter chat completions (`LLM_MODEL`, default `anthropic/claude-haiku-5.5`) with a forced `extract_receipt` tool call; retries on transient errors; `LLM_MOCK` scenarios |
| `category_suggestion` | Store-name → category: pg_trgm `find_similar_active` (threshold 0.3), then most-used in 90 days |
| `category_classifier` | Expense description → category via the decision model (below) |
| `rate_limiter` | Redis per-family daily counters: receipt uploads (50) and category suggests (500). Fails open on Redis errors |
| `jwt_service`, `google_oauth`, `grace_period` | Tokens, OAuth exchange, editable-month rule |
| `hpi_service`, `hpi_fetcher` | Keep the FHFA house price index ≤ 7 days old (background download; off in tests via `HPI_AUTO_REFRESH`) |

## LLM and decision-model seam

- **One client.** `app.main` lifespan builds a single `AsyncOpenAI` pointed at `LLM_BASE_URL`
  (OpenRouter) with `OPENROUTER_API_KEY`; routers get it via `app.dependencies.get_llm_client`
  and pass it into services. Do not construct new clients in services.
- **Receipts** use `client.chat.completions.create(...)` with the tool schema in `claude_client`.
- **Category decisions** use OpenRouter's System One endpoint, which is *not* a chat model and
  is not in `/models`: `client.with_options(timeout=DECISION_TIMEOUT_SECONDS, max_retries=0).post("/systemone", body=..., cast_to=object)`.
  Body: `{model: DECISION_MODEL, state: {expense_description}, questions: {category: {type: "choice", instructions, criteria: {name: hint|null}}}}`
  (criteria must be a map). Answer: `answers.category.{choice, probabilities, confidence}`.
  Accept only `confidence >= DECISION_MIN_CONFIDENCE` (0.5) and a case-insensitive match to an
  active category; otherwise trigram `find_similar_active`, otherwise `None`. Any exception is
  swallowed (outcome `error`) — a suggestion never fails the request. See
  [ADR 0002](../../../docs/adr/0002-category-suggester-decision-model.md).
- **Prompt-injection posture:** user text goes in `state` as data with fixed `instructions`;
  output is constrained to the family's category names and validated.
- **Mocks:** `LLM_MOCK` / `LLM_MOCK_SCENARIO` (`success`, `medium_confidence`, `low_confidence`,
  `non_receipt`, `api_error`; `ANTHROPIC_MOCK*` are legacy aliases) and `DECISION_MOCK` /
  `DECISION_MOCK_SCENARIO` (`success` = first active category at 0.95, `low_confidence`,
  `api_error`). Both are on in the dev overlay; tests force `DECISION_MOCK`.
- **Logging:** log outcome, confidence, ids, latency, model — never the description, receipt
  contents, or keys.
- Adding a provider or model call is a steering-doc trigger (root `AGENTS.md` PR rule); update
  `docs/architecture.md` and this file.
