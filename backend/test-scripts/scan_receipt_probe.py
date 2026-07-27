#!/usr/bin/env python3
"""Manual probe: run a receipt image through the real backend pipeline.

Bypasses the frontend and the HTTP layer — calls receipt_service.process_upload
directly, which is the exact code path POST /api/families/{id}/receipts uses.
Hits the real Anthropic API unless ANTHROPIC_MOCK=true.

Prints what the frontend would receive: the ReceiptUploadResponse body, plus the
Expense the backend created (category, cost, description/merchant, date).

Usage (from backend/):
    uv run python test-scripts/scan_receipt_probe.py [IMAGE] [options]

    IMAGE                 path to a receipt image (default: e2e/fixtures/sample-receipt.jpg)
    --family-id UUID      use an existing family instead of the scratch one
    --keep                don't delete the rows this script created
    --allow-mock          proceed even when ANTHROPIC_MOCK=true
    --model ID            override the Claude model id for this run only (default:
                           claude_client._MODEL — production behavior otherwise)
    --temperature FLOAT   sampling temperature for this run (default: the pinned
                           production value, claude_client.DEFAULT_TEMPERATURE)
    --no-temperature      omit the temperature key entirely — required for models
                           that reject it under a forced tool_choice
    --revision LABEL      free-text label echoed in the output/summary, to tag runs

Requires Postgres reachable at DATABASE_URL (i.e. `task up` running), and a real
ANTHROPIC_API_KEY in the repo-root .env. Each run costs a fraction of a cent.
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# backend/test-scripts/this_file.py -> repo root. Keeps the default fixture path
# working regardless of the cwd the script is invoked from.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
# `app` is only importable when backend/ is on the path; make that true even if
# the script is invoked from the repo root rather than from backend/.
sys.path.insert(0, str(BACKEND_ROOT))

from anthropic import AsyncAnthropic  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.category import Category  # noqa: E402
from app.models.expense import Expense  # noqa: E402
from app.models.family import Family  # noqa: E402
from app.models.family_member import FamilyMember  # noqa: E402
from app.models.receipt import Receipt  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import receipt_service  # noqa: E402
from app.services.claude_client import _MODEL, CATEGORY_LABELS, DEFAULT_TEMPERATURE  # noqa: E402

PROBE_EMAIL = "receipt-probe@local.test"
# The labels the extractor is allowed to emit, which are also the names a real
# family is seeded with. Using anything else here would make the probe's category
# matching a fiction: the hint would miss and every run would look like a
# fallback, even when the extraction was perfect.
PROBE_CATEGORIES = CATEGORY_LABELS


def money(cents: int | None) -> str:
    return "—" if cents is None else f"${cents / 100:,.2f}"


def rule(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m\n" + "─" * 68)


async def ensure_scratch_family(db) -> tuple[User, Family]:
    """Find-or-create a probe user + family + categories. Idempotent."""
    user = await db.scalar(select(User).where(User.email == PROBE_EMAIL))
    now = datetime.now(tz=timezone.utc)

    if user is None:
        user = User(
            id=uuid.uuid4(),
            google_id=f"probe_{uuid.uuid4().hex[:12]}",
            email=PROBE_EMAIL,
            display_name="Receipt Probe",
            created_at=now,
        )
        db.add(user)
        await db.flush()

    family = await db.scalar(
        select(Family).join(FamilyMember, FamilyMember.family_id == Family.id).where(FamilyMember.user_id == user.id)
    )
    if family is None:
        family = Family(id=uuid.uuid4(), name="Receipt Probe Family", created_by=user.id, created_at=now)
        db.add(family)
        await db.flush()
        db.add(FamilyMember(id=uuid.uuid4(), family_id=family.id, user_id=user.id, role="admin", joined_at=now))
        await db.flush()

    existing = set((await db.scalars(select(Category.name).where(Category.family_id == family.id))).all())
    for i, name in enumerate(PROBE_CATEGORIES):
        if name not in existing:
            db.add(
                Category(
                    id=uuid.uuid4(),
                    family_id=family.id,
                    name=name,
                    sort_order=i,
                    is_active=True,
                    created_at=now,
                )
            )
    await db.flush()
    return user, family


async def resolve_target(db, family_id: uuid.UUID | None) -> tuple[uuid.UUID, uuid.UUID, bool]:
    """Return (family_id, uploader_id, is_scratch)."""
    if family_id is None:
        user, family = await ensure_scratch_family(db)
        return family.id, user.id, True

    family = await db.get(Family, family_id)
    if family is None:
        sys.exit(f"No family with id {family_id}")
    member = await db.scalar(select(FamilyMember).where(FamilyMember.family_id == family_id).limit(1))
    if member is None:
        sys.exit(f"Family {family_id} has no members — cannot attribute the upload.")
    n_cats = len(
        (await db.scalars(select(Category.id).where(Category.family_id == family_id, Category.is_active))).all()
    )
    if n_cats == 0:
        sys.exit(f"Family {family_id} has no active categories — upload would 409.")
    return family_id, member.user_id, False


async def sweep_failed(db, family_id: uuid.UUID) -> None:
    """Delete this family's failed receipts + their preserved images.

    Phase-2 failures intentionally commit a status='failed' row and keep the
    image on disk for the retry endpoint. Useful in the app, just litter here.
    """
    rows = (await db.scalars(select(Receipt).where(Receipt.family_id == family_id, Receipt.status == "failed"))).all()
    for r in rows:
        if r.image_path:
            Path(r.image_path).unlink(missing_ok=True)
        await db.delete(r)
    await db.commit()
    if rows:
        print(f"\n  cleaned up {len(rows)} failed receipt row(s) + image(s)")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", default=str(REPO_ROOT / "e2e" / "fixtures" / "sample-receipt.jpg"))
    ap.add_argument("--family-id", type=uuid.UUID, default=None)
    ap.add_argument("--keep", action="store_true", help="keep the receipt/expense rows this run created")
    ap.add_argument("--allow-mock", action="store_true")
    ap.add_argument("--model", default=None, help="override the Claude model id for this run only")
    ap.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"sampling temperature for this run (default: {DEFAULT_TEMPERATURE}, the pinned production value)",
    )
    ap.add_argument(
        "--no-temperature",
        action="store_true",
        help="omit the temperature key entirely; required for models that reject it under a forced tool_choice",
    )
    ap.add_argument("--revision", default=None, help="free-text label echoed in the output, to tag runs")
    args = ap.parse_args()

    effective_temperature = None if args.no_temperature else args.temperature

    usage: dict[str, int] = {}

    def _capture_usage(u) -> None:
        usage["input_tokens"] = u.input_tokens
        usage["output_tokens"] = u.output_tokens

    effective_model = args.model or _MODEL

    def print_summary(name=None, total=None, date_=None, category=None) -> None:
        """Compact, grep/parse-friendly summary block, printed at the end of every run."""
        rule("Summary")
        print(
            "SUMMARY "
            + json.dumps(
                {
                    "model": effective_model,
                    "temperature": effective_temperature if effective_temperature is not None else "omitted",
                    "revision": args.revision,
                    "name": name,
                    "total": total,
                    "date": date_,
                    "category": category,
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                }
            )
        )

    image_path = Path(args.image)
    if not image_path.is_file():
        sys.exit(f"No such image: {image_path}")
    raw = image_path.read_bytes()

    rule("Configuration")
    key = settings.anthropic_api_key
    key_desc = f"{key[:7]}…({len(key)} chars)" if key else "<empty>"
    if args.model:
        print(f"  model             {effective_model}  (override, default is {_MODEL})")
    else:
        print(f"  model             {effective_model}  (from claude_client._MODEL)")
    if effective_temperature is None:
        print("  temperature       omitted (not sent)")
    else:
        print(f"  temperature       {effective_temperature}  (production default is {DEFAULT_TEMPERATURE})")
    print(f"  revision          {args.revision or '—'}")
    print(f"  ANTHROPIC_MOCK    {settings.anthropic_mock}")
    print(f"  ANTHROPIC_API_KEY {key_desc}")
    print(f"  storage path      {settings.receipt_storage_path}")
    print(f"  image             {image_path}  ({len(raw):,} bytes)")

    if settings.anthropic_mock and not args.allow_mock:
        sys.exit("\nANTHROPIC_MOCK=true — this would return canned data. Set it false, or pass --allow-mock.")
    if not settings.anthropic_mock and not key.startswith("sk-ant-"):
        print("\n\033[33m  warning: key does not look like a real sk-ant-… key; expect a 401 → 503\033[0m")

    client = AsyncAnthropic(api_key=key)
    created: dict[str, uuid.UUID] = {}

    async with AsyncSessionLocal() as db:
        family_id, uploader_id, is_scratch = await resolve_target(db, args.family_id)
        print(f"  family            {family_id}{'  (scratch)' if is_scratch else ''}")
        print(f"  uploader          {uploader_id}")

        rule("Calling receipt_service.process_upload()")
        try:
            receipt, expense, needs_edit = await receipt_service.process_upload(
                db,
                client,
                family_id,
                uploader_id,
                raw,
                model=args.model,
                temperature=effective_temperature,
                usage_callback=_capture_usage,
            )
        except HTTPException as exc:
            await db.commit()  # persist the failed Receipt audit row
            rule("Backend returned an error")
            print(f"  HTTP {exc.status_code}")
            print(f"  detail: {exc.detail}")
            print("\n  This is exactly the error body the frontend would show.")
            print("  The real cause is in the log line above (the 503 detail is deliberately generic).")
            if not args.keep:
                await sweep_failed(db, family_id)
            print_summary()
            await client.close()
            return 1

        await db.commit()
        created["receipt"] = receipt.id
        created["expense"] = expense.id

        category = await db.get(Category, expense.category_id)

        rule("What the API returns to the frontend (ReceiptUploadResponse)")
        print(
            json.dumps(
                {
                    "receipt": {
                        "id": str(receipt.id),
                        "status": receipt.status,
                        "parsed_merchant": receipt.parsed_merchant,
                        "parsed_total_cents": receipt.parsed_total_cents,
                        "parsed_date": str(receipt.parsed_date) if receipt.parsed_date else None,
                        "raw_response": receipt.raw_response,
                        "error_message": receipt.error_message,
                        "image_path": receipt.image_path,
                    },
                    "expense_id": str(expense.id),
                    "needs_edit": needs_edit,
                },
                indent=2,
            )
        )

        rule("The Expense the backend created (what lands in the expense list)")
        print(f"  name / merchant   {receipt.parsed_merchant or '—'}")
        print(f"  description       {expense.description}")
        extracted_category = (receipt.raw_response or {}).get("category")
        print(f"  extracted label   {extracted_category or '—'}   (what Claude classified it as)")
        print(f"  category          {category.name if category else '?'}   (id {expense.category_id})")
        print(f"  cost              {money(expense.amount_cents)}")
        print(f"  expense_date      {expense.expense_date}   (year_month {expense.year_month})")
        print(f"  needs_edit        {needs_edit}")

        if needs_edit:
            if expense.amount_cents == 0:
                cause = "low confidence or no total extracted, so the amount is stored as $0.00"
            else:
                cause = (
                    f"neither the extracted label ({extracted_category or 'none'}) nor the store "
                    "name matched a\n  category, so the expense fell back to an arbitrary active "
                    "one — the extracted amount is kept as-is"
                )
            print(f'\n  \033[33mneeds_edit=True → the UI shows a "Needs review" chip.\n  Cause: {cause}.\033[0m')

        if receipt.parsed_total_cents is not None and expense.amount_cents != receipt.parsed_total_cents:
            print(
                f"\n  note: receipt parsed {money(receipt.parsed_total_cents)} but the expense "
                f"stores {money(expense.amount_cents)}"
            )

        if not args.keep:
            await db.execute(delete(Expense).where(Expense.id == expense.id))
            await db.execute(delete(Receipt).where(Receipt.id == receipt.id))
            await db.commit()
            if receipt.image_path:
                Path(receipt.image_path).unlink(missing_ok=True)
            print("\n  cleaned up receipt + expense rows (pass --keep to retain them)")
        else:
            print(f"\n  kept: receipt={created['receipt']} expense={created['expense']}")

        print_summary(
            name=receipt.parsed_merchant,
            total=(receipt.parsed_total_cents / 100 if receipt.parsed_total_cents is not None else None),
            date_=str(receipt.parsed_date) if receipt.parsed_date else None,
            category=extracted_category,
        )

    await client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
