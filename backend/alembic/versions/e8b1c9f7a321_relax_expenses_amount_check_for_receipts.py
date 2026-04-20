"""relax expenses amount CHECK to allow zero for low-confidence receipts

Revision ID: e8b1c9f7a321
Revises: c4e2f1b3d5a8
Create Date: 2026-04-19 12:00:00.000000

Spec §Unit 3 requires low-confidence Claude responses to persist an Expense
with ``amount_cents=0`` so that the frontend "Needs review" chip (keyed on
``receipt_status === 'completed' && amount_cents === 0``) fires. The original
CHECK constraint required ``amount_cents > 0``; this migration relaxes it to
``amount_cents >= 0``.

Manual expense entry forms still enforce ``amount_cents > 0`` at the
application/schema layer; the DB-level constraint is loosened only so that
receipt scanning can record a placeholder row for user review.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8b1c9f7a321"
down_revision: Union[str, None] = "c4e2f1b3d5a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the strict "> 0" constraint and replace with ">= 0".
    op.drop_constraint("ck_expenses_amount_positive", "expenses", type_="check")
    op.create_check_constraint(
        "ck_expenses_amount_positive",
        "expenses",
        "amount_cents >= 0",
    )


def downgrade() -> None:
    # Revert to the original strict "> 0" constraint. Any zero-amount rows
    # (i.e. low-confidence receipts awaiting review) must be cleaned up first.
    op.drop_constraint("ck_expenses_amount_positive", "expenses", type_="check")
    op.create_check_constraint(
        "ck_expenses_amount_positive",
        "expenses",
        "amount_cents > 0",
    )
