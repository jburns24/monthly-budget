"""SQLAlchemy implementation of :class:`~app.ports.read_models.BudgetQuery`.

The five-way aggregate ``expense_service.get_budget_summary`` used to run
inline: categories LEFT JOIN expenses LEFT JOIN a goals subquery, GROUP BY. This
module is the SQL half of the Step 5 split — the percentage/status/total math
now lives in the pure ``expense_service.build_budget_summary``, unit-tested with
literal :class:`~app.ports.read_models.CategorySpendRow` data, no DB.
"""

from uuid import UUID

from sqlalchemy import Exists, case, func, literal, outerjoin, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.expense import Expense
from app.models.monthly_goal import MonthlyGoal
from app.ports.read_models import CategorySpendRow


class SqlAlchemyBudgetQuery:
    """Budget summary reads against Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def category_spend_and_goals(self, family_id: UUID, year_month: str) -> list[CategorySpendRow]:
        goal_subq = (
            select(MonthlyGoal.category_id, MonthlyGoal.amount_cents)
            .where(
                MonthlyGoal.family_id == family_id,
                MonthlyGoal.year_month == year_month,
            )
            .subquery()
        )

        expenses_filtered = outerjoin(
            Category,
            Expense,
            (Expense.category_id == Category.id)
            & (Expense.family_id == family_id)
            & (Expense.year_month == year_month)
            & (Expense.entry_type == "expense"),
        ).outerjoin(
            goal_subq,
            goal_subq.c.category_id == Category.id,
        )

        stmt = (
            select(
                Category.id,
                Category.name,
                Category.icon,
                func.coalesce(func.sum(Expense.amount_cents), 0).label("spent_cents"),
                goal_subq.c.amount_cents.label("goal_cents"),
            )
            .select_from(expenses_filtered)
            .where(
                Category.family_id == family_id,
                Category.is_active.is_(True),
            )
            .group_by(Category.id, Category.name, Category.icon, goal_subq.c.amount_cents)
            .order_by(Category.sort_order, Category.name)
        )

        result = await self._session.execute(stmt)
        return [
            CategorySpendRow(
                category_id=row.id,
                category_name=row.name,
                icon=row.icon,
                spent_cents=int(row.spent_cents),
                goal_cents=int(row.goal_cents) if row.goal_cents is not None else None,
            )
            for row in result.all()
        ]

    async def month_totals(self, family_id: UUID, year_month: str) -> tuple[int, int]:
        stmt = select(
            func.coalesce(
                func.sum(case((Expense.entry_type == "income", Expense.amount_cents), else_=0)),
                0,
            ).label("income_cents"),
            func.coalesce(
                func.sum(case((Expense.entry_type == "expense", Expense.amount_cents), else_=0)),
                0,
            ).label("spent_cents"),
        ).where(
            Expense.family_id == family_id,
            Expense.year_month == year_month,
        )
        row = (await self._session.execute(stmt)).one()
        return int(row.income_cents), int(row.spent_cents)

    async def has_starting_balance(self, family_id: UUID, year_month: str) -> bool:
        exists_stmt = select(
            Exists(
                select(literal(1)).where(
                    Expense.family_id == family_id,
                    Expense.year_month == year_month,
                    Expense.is_starting_balance.is_(True),
                )
            )
        )
        return bool((await self._session.execute(exists_stmt)).scalar_one())
