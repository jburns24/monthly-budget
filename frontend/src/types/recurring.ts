import type { EntryType } from './expenses'

export type Frequency = 'weekly' | 'biweekly' | 'monthly' | 'yearly'

export const FREQUENCY_LABELS: Record<Frequency, string> = {
  weekly: 'Weekly',
  biweekly: 'Every 2 weeks',
  monthly: 'Monthly',
  yearly: 'Yearly',
}

export interface RecurringExpense {
  id: string
  family_id: string
  category_id: string | null
  amount_cents: number
  description: string
  entry_type: EntryType
  frequency: Frequency
  start_date: string
  end_date: string | null
  next_due_date: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface RecurringExpenseCreate {
  amount_cents: number
  description?: string
  category_id?: string | null
  entry_type?: EntryType
  frequency: Frequency
  start_date: string
  end_date?: string | null
}

export interface RecurringExpenseUpdate {
  amount_cents?: number
  description?: string
  category_id?: string
  frequency?: Frequency
  next_due_date?: string
  end_date?: string | null
  is_active?: boolean
}

export interface RecurringExpenseListResponse {
  recurring_expenses: RecurringExpense[]
}
