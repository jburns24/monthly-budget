export interface CategoryBrief {
  id: string
  name: string
  icon: string | null
}

export interface UserBrief {
  id: string
  display_name: string
}

export interface Expense {
  id: string
  family_id: string
  category: CategoryBrief
  created_by_user: UserBrief
  amount_cents: number
  description: string
  expense_date: string
  created_at: string
  updated_at: string
}

export interface ExpenseCreate {
  amount_cents: number
  description?: string
  category_id: string
  expense_date: string
}

export interface ExpenseUpdate {
  amount_cents?: number
  description?: string
  category_id?: string
  expense_date?: string
  expected_updated_at: string
}

export interface ExpenseListResponse {
  expenses: Expense[]
  total_count: number
  page: number
  per_page: number
}

export interface BudgetCategorySummary {
  category_id: string
  category_name: string
  icon: string | null
  spent_cents: number
  goal_cents: number | null
  percentage: number
  status: string
}

export interface BudgetSummaryResponse {
  year_month: string
  total_spent_cents: number
  categories: BudgetCategorySummary[]
}
