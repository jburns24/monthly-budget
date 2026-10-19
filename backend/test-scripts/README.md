# test-scripts

Manual probes for exercising backend code paths that the automated test suite
deliberately mocks. These are **not** collected by pytest (`testpaths = ["tests"]`)
and are not run in CI — they are developer tools you invoke by hand.

## scan_receipt_probe.py

Runs a receipt image through the real receipt-scanning pipeline, **including a
live call to the OpenRouter API** (Claude Haiku via its OpenAI-compatible endpoint), and prints what the backend would return to
the frontend.

The whole automated suite mocks `AsyncOpenAI`, so nothing in `tests/` or the
Playwright e2e suite ever proves the real Claude call works. This script is how
you check that.

```bash
cd backend
uv run python test-scripts/scan_receipt_probe.py                    # bundled fixture receipt
uv run python test-scripts/scan_receipt_probe.py ~/Desktop/lunch.jpg
uv run python test-scripts/scan_receipt_probe.py --keep             # leave rows in the DB
uv run python test-scripts/scan_receipt_probe.py --family-id <uuid> # use one of your families
```

### Requirements

- Postgres and Redis running (`task up`).
- A real `OPENROUTER_API_KEY` in the repo-root `.env`. The committed placeholder
  produces a 401, which the pipeline surfaces as a generic HTTP 503.
- `LLM_MOCK` (or the legacy `ANTHROPIC_MOCK`) unset or `false`. The script refuses to run under mock mode
  unless you pass `--allow-mock`, since canned data defeats the point.

### What it exercises

Calls `receipt_service.process_upload()` directly — the same function
`POST /api/families/{family_id}/receipts` calls — so it covers MIME validation,
EXIF stripping and JPEG re-encoding (images are never persisted), the Claude extraction
call, category suggestion, and Expense creation. It skips only the HTTP and auth
layers.

Output is the `ReceiptUploadResponse` JSON plus the resulting Expense broken out
by merchant, description, category, cost, and date.

### Scratch data

Without `--family-id` it find-or-creates a `receipt-probe@local.test` user and a
"Receipt Probe Family" with five categories, so category suggestion has a real
choice to make instead of trivially falling back to the only option. The user and
family persist between runs; the receipt and expense rows are deleted afterward
unless you pass `--keep`.

Note that a Phase-2 failure intentionally commits a `status='failed'` receipt row
as an audit trail (the image itself is never stored; the user re-uploads). The
script sweeps those too, so repeated failed runs don't accumulate.

### Cost

One receipt is roughly 1,300 visual tokens against `LLM_MODEL` (default
`anthropic/claude-haiku-5.5`) — a fraction of a cent per run at Haiku-class
pricing. Check OpenRouter's activity page for the exact charge.
