# T02 Rollup Proof Summary — Claude Adapter with Deterministic Mock

**Task**: T02 — Claude Adapter with Deterministic Mock (rollup)
**Date**: 2026-04-19
**Status**: COMPLETED

## Sub-Task Commits

| Sub-task | Description | Commit | Tests |
|----------|-------------|--------|-------|
| T02.1 (#7) | AsyncAnthropic lifespan singleton + config | 236dd39 | 7/7 |
| T02.4 (#10) | Dev-only mock-claude toggle route | 8120bf4 | covered |
| T02.2 (#8) | extract_receipt with request builder, parser, retry | 76fc8b8 | 12/12 |
| T02.3 (#9) | Mock branch with 5 deterministic scenarios | 9e4749e | 7/7 |

## Rollup Artifacts

| File | Type | Status | Description |
|------|------|--------|-------------|
| T02-01-test.txt | test | PASS | 26/26 tests across all T02 test files |
| T02-02-cli.txt | cli | PASS | Integration summary: settings, mock scenarios, route |

## Architecture Delivered

```
app.state.anthropic (AsyncAnthropic singleton, lifespan-managed)
    ↓
get_anthropic_client(request) → FastAPI dependency
    ↓
extract_receipt(client, image_bytes, media_type)
    ├── settings.anthropic_mock=True → _get_mock_response(scenario)
    │       success → ExtractedReceipt(is_receipt=True, confidence="high", total=42.50, date="2026-03-21")
    │       medium_confidence → ExtractedReceipt(confidence="medium", no date)
    │       low_confidence → ExtractedReceipt(confidence="low", no fields)
    │       non_receipt → ExtractedReceipt(is_receipt=False)
    │       api_error → raises APIStatusError(503)
    └── settings.anthropic_mock=False → _call_claude(client, ...) [tenacity retry]
            model: claude-haiku-4-5-20251001
            tool_use: extract_receipt tool
            retry: 3 attempts, exponential backoff, 429/5xx/connection errors

POST /api/dev/mock-claude?scenario=<name>  (dev/test only)
    → sets settings.anthropic_mock=True + scenario in-process
```

## Test Coverage (26 tests, 0.49s)

- T02.1: 7 tests (config defaults, lifespan wiring, dependency injection)
- T02.2: 12 tests (request builder, tool-use parser, tenacity retry behavior)
- T02.3: 7 tests (all 5 scenarios + disabled=real client + unknown=fallback)
