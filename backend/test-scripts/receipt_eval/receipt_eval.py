#!/usr/bin/env python3
"""Receipt / order-screenshot extraction eval (no database needed).

Runs images through the same code the upload endpoint uses -- MIME validation,
JPEG re-encode (receipt_storage), the live extraction call (claude_client, i.e.
the production system prompt), the date guard from receipt_service, and the
Decision-1 category suggestion -- and prints / scores what the app would store.

One image (prints the result; scores it too if its filename is in cases.json):

    cd backend
    uv run python test-scripts/receipt_eval/receipt_eval.py path/to/screenshot.png

The whole suite (hill-climbing loop; scores every case in cases.json):

    uv run python test-scripts/receipt_eval/receipt_eval.py --suite --repeat 2
    uv run python test-scripts/receipt_eval/receipt_eval.py --suite --only ebay_crop,etsy_mobile
    uv run python test-scripts/receipt_eval/receipt_eval.py --suite --cases my-local-cases.json --save run.json

Needs OPENROUTER_API_KEY in the environment or the repo-root .env. Costs a
fraction of a cent per call (Haiku). Never prints the key.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
BACKEND_ROOT = HERE.parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import structlog  # noqa: E402
from openai import AsyncOpenAI  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import category_classifier, claude_client, receipt_service, receipt_storage  # noqa: E402
from app.services.category_service import _DEFAULT_CATEGORIES  # noqa: E402

CATEGORIES = [SimpleNamespace(name=name) for name, _icon, _order in _DEFAULT_CATEGORIES]
DEFAULT_CASES = HERE / "cases.json"


def pin_today(today: date) -> None:
    """Make date.today() return a fixed day inside the modules that read it.

    Fixture dates are fixed, so "today" must be fixed too or the prompt's
    "this month" bias and the stale/future date guards would change the answer.
    """

    class _Pinned(date):
        @classmethod
        def today(cls):  # noqa: D401
            return today

    claude_client.date = _Pinned  # type: ignore[attr-defined]
    receipt_service.date = _Pinned  # type: ignore[attr-defined]


def prompt_hash() -> str:
    text = claude_client._build_system_prompt(date(2026, 1, 1)) + json.dumps(claude_client._TOOL_DEFINITION)
    return hashlib.sha256(text.encode()).hexdigest()[:10]


async def run_one(client: AsyncOpenAI, path: Path, classify: bool) -> dict:
    raw = path.read_bytes()
    mime = receipt_storage.validate_mime(raw)
    jpeg, size = receipt_storage.sanitize_image(raw)
    usage: dict[str, int] = {}

    def _usage(u) -> None:
        usage["in"], usage["out"] = u.prompt_tokens, u.completion_tokens

    extracted = await claude_client.extract_receipt(client, jpeg, media_type="image/jpeg", usage_callback=_usage)
    parsed_date = receipt_service._parse_expense_date(extracted.date)
    result = {
        "mime": mime,
        "size": list(size),
        "is_receipt": extracted.is_receipt,
        "confidence": extracted.confidence,
        "name": extracted.store_name,
        "total": extracted.total_amount,
        "raw_date": extracted.date,
        "date": parsed_date.isoformat() if parsed_date else None,
        "description": extracted.description,
        "category": None,
        "category_confidence": None,
        "tokens": usage,
    }
    classifier_input = extracted.description or extracted.store_name
    if classify and extracted.is_receipt and classifier_input:
        try:
            answer = await category_classifier._ask_model(client, classifier_input, CATEGORIES)
            conf = answer.get("confidence")
            result["category_confidence"] = conf
            if isinstance(conf, int | float) and conf >= settings.decision_min_confidence:
                match = category_classifier._match(CATEGORIES, answer.get("choice"))
                result["category"] = match.name if match else None
            else:
                result["category"] = "(low confidence)"
        except Exception as exc:  # noqa: BLE001
            result["category"] = f"(error: {type(exc).__name__})"
    return result


def _any_in(text: str | None, needles: list[str]) -> bool:
    low = (text or "").lower()
    return any(n.lower() in low for n in needles)


def score(result: dict, expect: dict) -> dict[str, str]:
    """Return {check: 'pass' | 'soft' | 'FAIL: why'} for each expectation."""
    out: dict[str, str] = {}
    if "is_receipt" in expect:
        out["is_receipt"] = (
            "pass" if result["is_receipt"] == expect["is_receipt"] else f"FAIL: got {result['is_receipt']}"
        )
        if not expect["is_receipt"]:
            return out
    if not result["is_receipt"]:
        return {**out, "extraction": "FAIL: rejected as not a receipt"}
    out["desc_clean"] = (
        "FAIL: placeholder in description " + repr(result["description"])
        if re.search(r"unknown|n/a|<|>|\bnull\b", result["description"] or "", re.I)
        else "pass"
    )
    if result["name"] and result["name"].lower() not in (result["description"] or "").lower():
        out["desc_names_store"] = f"FAIL: {result['name']!r} not in {result['description']!r}"
    if "total" in expect:
        got = result["total"]
        want = expect["total"]  # null means "no total is printed; must not be invented"
        ok = got is None if want is None else (got is not None and abs(got - want) < 0.005)
        out["total"] = "pass" if ok else f"FAIL: got {got}"
    if "date" in expect:  # null means "must not invent a date"
        got = result["date"]
        out["date"] = "pass" if got == expect["date"] else f"FAIL: got {got} (raw {result['raw_date']})"
    if "name" in expect:
        got = result["name"]
        if got and any(re.search(p, got, re.I) for p in expect["name"]):
            out["name"] = "pass"
        elif got is None and expect.get("name_ok_if_null"):
            out["name"] = "soft"
        elif got and any(re.search(p, got, re.I) for p in expect.get("name_soft", [])):
            out["name"] = "soft"
        else:
            out["name"] = f"FAIL: got {got!r}"
    for i, group in enumerate(expect.get("description_all", [])):
        ok = _any_in(result["description"], group)
        out[f"desc[{'|'.join(group)}]"] = "pass" if ok else f"FAIL: {result['description']!r}"
    if "category_any" in expect and "category" in result:
        got = result["category"]
        out["category"] = "pass" if got in expect["category_any"] else f"FAIL: got {got}"
    return out


def case_verdict(checks: dict[str, str]) -> str:
    if any(v.startswith("FAIL") for v in checks.values()):
        return "FAIL"
    return "soft" if "soft" in checks.values() else "pass"


def fmt_result(r: dict) -> str:
    total = f"${r['total']:.2f}" if isinstance(r["total"], int | float) else "—"
    return (
        f"receipt={r['is_receipt']} conf={r['confidence']} name={r['name']!r} total={total} "
        f"date={r['date']}(raw {r['raw_date']}) cat={r['category']}\n      desc: {r['description']!r}"
    )


async def main() -> int:
    # keep the per-call structlog chatter out of the report
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="a single image to run (png/jpg/webp/heic)")
    ap.add_argument("--suite", action="store_true", help="run every case in --cases")
    ap.add_argument("--cases", default=str(DEFAULT_CASES), help="cases.json to score against")
    ap.add_argument("--only", default=None, help="comma-separated case ids (suite mode)")
    ap.add_argument("--repeat", type=int, default=1, help="runs per image (the model is not deterministic)")
    ap.add_argument("--no-classify", action="store_true", help="skip the Decision-1 category call")
    ap.add_argument("--today", default=None, help="pin today's date (YYYY-MM-DD); suites default to cases.json")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--save", default=None, help="write full results as JSON to this path")
    ap.add_argument("--show-prompt", action="store_true", help="print the system prompt and exit")
    args = ap.parse_args()

    if args.show_prompt:
        print(claude_client._build_system_prompt(date.today()))
        return 0
    if not args.suite and not args.image:
        ap.error("pass an IMAGE path or --suite")
    if not settings.openrouter_api_key:
        sys.exit("OPENROUTER_API_KEY is not set (environment or repo-root .env).")
    if settings.llm_mock:
        sys.exit("LLM_MOCK=true would return canned data; unset it.")

    spec = json.loads(Path(args.cases).read_text())
    base = Path(args.cases).resolve().parent
    known_case = None
    if args.image and not args.suite:
        known_case = next((c for c in spec["cases"] if Path(c["image"]).stem == Path(args.image).stem), None)
    # Fixture expectations assume cases.json's pinned "today"; a lone unknown image
    # (e.g. the user's real screenshot) is judged against the real clock.
    today_str = args.today or (spec.get("today") if (args.suite or known_case) else None)
    if today_str:
        pin_today(date.fromisoformat(today_str))

    jobs: list[tuple[str, Path, dict | None]] = []
    if args.suite:
        only = set(args.only.split(",")) if args.only else None
        for c in spec["cases"]:
            if only and c["id"] not in only:
                continue
            p = (base / c["image"]).resolve()
            if not p.is_file():
                print(f"  skip {c['id']}: {p} missing")
                continue
            jobs.append((c["id"], p, c.get("expect")))
    else:
        p = Path(args.image).expanduser()
        if not p.is_file():
            sys.exit(f"No such image: {p}")
        jobs.append((p.name, p, known_case.get("expect") if known_case else None))

    client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=settings.openrouter_api_key, max_retries=2)
    sem = asyncio.Semaphore(args.concurrency)
    calls = 0

    async def go(cid: str, path: Path, expect: dict | None, n: int) -> dict:
        nonlocal calls
        async with sem:
            calls += 1
            try:
                res = await run_one(client, path, not args.no_classify)
            except Exception as exc:  # noqa: BLE001
                return {"id": cid, "run": n, "error": f"{type(exc).__name__}: {str(exc)[:200]}", "verdict": "FAIL"}
        entry = {"id": cid, "run": n, "result": res}
        if expect:
            entry["checks"] = score(res, expect)
            entry["verdict"] = case_verdict(entry["checks"])
        return entry

    print(f"model={settings.llm_model} prompt={prompt_hash()} today={today_str or date.today()} repeat={args.repeat}")
    entries = await asyncio.gather(*(go(c, p, e, n) for c, p, e in jobs for n in range(args.repeat)))
    await client.close()

    by_case: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by_case[e["id"]].append(e)

    passed = total_runs = 0
    for cid, runs in by_case.items():
        verdicts = [r["verdict"] for r in runs if "verdict" in r]
        good = sum(v in ("pass", "soft") for v in verdicts)
        passed += good
        total_runs += len(verdicts)
        tag = f"{good}/{len(verdicts)}" if verdicts else "n/a"
        print(f"\n{cid}  [{tag}]")
        for r in runs:
            if "error" in r:
                print(f"  run {r['run']}: ERROR {r['error']}")
                continue
            mark = {"pass": "PASS", "soft": "soft", "FAIL": "FAIL"}.get(r.get("verdict", ""), "    ")
            print(f"  run {r['run']}: {mark} {fmt_result(r['result'])}")
            for k, v in r.get("checks", {}).items():
                if v != "pass":
                    print(f"      {k}: {v}")

    if total_runs:
        print(
            f"\nSCORE {passed}/{total_runs} runs ({100 * passed / total_runs:.0f}%)  api_calls={calls}  prompt={prompt_hash()}"
        )
    if args.save:
        Path(args.save).write_text(json.dumps({"prompt": prompt_hash(), "entries": entries}, indent=2))
    return 0 if passed == total_runs else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
