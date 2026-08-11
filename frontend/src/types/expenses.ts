import type { ReceiptStatus } from '@/types/receipts'

export type EntryType = 'expense' | 'income'

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
  category: CategoryBrief | null
  created_by_user: UserBrief
  amount_cents: number
  description: string
  expense_date: string
  created_at: string
  updated_at: string
  entry_type: EntryType
  is_starting_balance: boolean
  receipt_id: string | null
  receipt_status: ReceiptStatus | null
}

export interface ExpenseCreate {
  amount_cents: number
  description?: string
  category_id?: string | null
  expense_date: string
  entry_type?: EntryType
  is_starting_balance?: boolean
}

export interface ExpenseUpdate {
  amount_cents?: number
  description?: string
  category_id?: string | null
  expense_date?: string
  entry_type?: EntryType
  is_starting_balance?: boolean
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
  total_income_cents: number
  has_starting_balance: boolean
  categories: BudgetCategorySummary[]
  is_editable?: boolean
}
