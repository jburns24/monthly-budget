# Category suggester uses Microsoft Decision 1 via OpenRouter System One

When a user types an expense description in **Create Expense**, the app pre-selects a likely
category (`POST /api/families/{family_id}/categories/suggest`, `app/services/category_classifier.py`,
shipped in #28 / backend 0.11.0). This records how that suggestion is made.

**Decision.** Ask OpenRouter's Decisions ("System One") endpoint, `POST {LLM_BASE_URL}/systemone`,
with model `microsoft/microsoft-decision-1` (`DECISION_MODEL`). The request is one `choice`
question whose criteria are the family's active category names (the six seeded categories carry a
short hint; custom ones pass `null`), with the description in `state` as data. The model returns
`choice`, per-option `probabilities` and a `confidence`; we accept the choice only when
`confidence >= 0.5` (`DECISION_MIN_CONFIDENCE`) and it case-insensitively matches an active
category.

**Why this model.** It is purpose-built for constrained classification: output is limited to
the supplied options and comes with a calibrated confidence we can threshold, so there is no
free-text parsing and no tool-schema prompt to maintain. It is not listed in OpenRouter's
`/models` and does not speak chat completions, but it is reached with the same API key and the
same `AsyncOpenAI` client (`client.post("/systemone", ...)`). Live trials returned the expected
category at ≥ 0.99 confidence for clear merchants in ~250–650 ms, and an injected
"answer Bills" instruction did not change the answer.

**Fallback path.** Below threshold, on an invalid choice, or on any error: pg_trgm similarity of
the description against category names (`find_similar_active`, threshold 0.3), then `null`.
The endpoint always returns 200 with `{category_id, category_name}` (both possibly `null`);
a suggestion never fails or blocks expense entry.

**Timeout / retries.** 3 s (`DECISION_TIMEOUT_SECONDS`) and `max_retries=0`. The call happens on
Description blur while the user is still filling the form; a late answer is worse than none.

**Mock.** `DECISION_MOCK=true` (dev overlay and all tests) skips the network;
`DECISION_MOCK_SCENARIO` = `success` (first active category at 0.95), `low_confidence` (0.1), or
`api_error`. Production pins `DECISION_MOCK=false` in the homelab ConfigMap.

**Rate limit.** 500 suggestions per family per day in Redis
(`categories:suggest:{family_id}:{date}`), 429 with `Retry-After` beyond that; fails open if Redis
is unavailable, like the receipt limiter.

**Manual pick wins.** The frontend only applies a suggestion when the request is still current
(stale ones are aborted), the description is ≥ 3 characters, the entry is an expense, and the
user has not changed the category select in this dialog session. A suggestion does replace the
localStorage last-used default. Edit and income dialogs do not suggest.

**Scanned receipts use the same path.** The receipt extractor (`claude_client`, chat model) no
longer chooses a category. Its forced tool call returns a short "what was bought and where" line
(`description`, e.g. "Groceries (milk, eggs, bread) at Safeway", capped at 120 characters). That
line becomes the Expense description and is passed to `suggest_category`, with the same threshold,
fallback and timeout. A classifier miss or error never fails the upload: the extraction is kept and
the expense lands on the first active category with `needs_edit=True`. This replaces the old
heuristic: trigram on the extractor's fixed six-label category, then the store name, then the most
used category in 90 days. That heuristic could not use a family's custom categories. The receipt
call is not counted against the suggest limit. The 50-per-day receipt-upload limit already caps it
at one decision call per upload, and charging it to the suggest budget would let scanning use up
the typing budget.

**Privacy / logging.** The description is never logged; logs carry outcome, confidence,
category id, latency and model.

**Considered options:** a chat model with a JSON/tool schema (reuses `LLM_MODEL`, but needs
output parsing and gives no calibrated confidence); trigram/usage heuristics only (free, but
cannot map "Starbucks latte" to "Dining"); a client-side keyword list (brittle, per-family
categories). Known weakness: nonsense input can still get a confident `Other`; the 3-character
minimum and manual-pick-wins contain it.
