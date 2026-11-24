# receipt_eval — receipt and order-screenshot extraction eval

A database-free harness for tuning the extraction prompt in
`app/services/claude_client.py`. It runs images through the same code the upload
endpoint uses (MIME check, JPEG re-encode, the live extraction call with the
production prompt, the date guard, and the Decision-1 category suggestion) and
scores the result against known ground truth.

Needs only `OPENROUTER_API_KEY` (environment or repo-root `.env`). No Postgres or
Redis. Roughly 4–5k input tokens per image on Haiku, a fraction of a cent per call.

## Run one image (e.g. your own order screenshot)

```bash
cd backend
uv run python test-scripts/receipt_eval/receipt_eval.py path/to/screenshot.png
```

Prints what the app would store: `is_receipt`, merchant, total, date (raw and after
the date guard), the description, and the category the decision model picks. If
the file's name matches a case in `cases.json`, it is also scored.

## Run the suite (the hill-climbing loop)

```bash
uv run python test-scripts/receipt_eval/receipt_eval.py --suite --repeat 3
uv run python test-scripts/receipt_eval/receipt_eval.py --suite --only ebay_crop,etsy_mobile
uv run python test-scripts/receipt_eval/receipt_eval.py --suite --cases ~/my-cases.json --save run.json
```

The model is not deterministic, so use `--repeat 3` or more when comparing prompts.
The last line is `SCORE n/m runs`, plus a hash of the prompt so runs can be tied
to the prompt revision that produced them. `--show-prompt` prints the prompt.

Loop: edit `_build_system_prompt` → run `--suite --repeat 3` → read the FAIL lines →
repeat. Keep the paper-receipt cases (`group: paper`) green to catch regressions.

## Files

- `cases.json` — ground truth. `today` is pinned (2026-11-24) so fixture dates never
  rot. `expect` keys: `is_receipt`, `total` (null = must not be invented), `date`
  (null = must not report one), `name` regexes (`name_ok_if_null`, `name_soft` =
  weaker but acceptable), `description_all` (groups of any-of keywords), and
  `category_any`. Every case also checks the description has no placeholder text
  ("UNKNOWN", "null") and names the store when one was reported.
- `fixtures/` — synthetic screenshots (fake names, addresses, order numbers):
  eBay (cropped detail panel on desktop and mobile width, with an eBay header, a
  held-out layout, and one cut off before the total), Amazon (order details, order
  list, mobile, dark mode), Etsy, Target, Walmart, DoorDash, a Best Buy order
  e-mail, a shopping cart that must be rejected, and a paper receipt.
- `make_fixtures.py` — regenerates the PNGs from HTML with headless Chrome
  (`pip install playwright`; uses the system Chrome). Not needed to run the eval.

## Adding your own case

Drop the screenshot somewhere, run it once with the single-image command, then add an
entry to a local cases file (`--cases`). Do not commit real screenshots: they carry
addresses and order numbers.
