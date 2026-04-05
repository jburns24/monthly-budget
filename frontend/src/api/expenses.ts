import { apiClient } from './client'
import type {
  Expense,
  ExpenseCreate,
  ExpenseUpdate,
  ExpenseListResponse,
  BudgetSummaryResponse,
} from '../types/expenses'

export async function getExpenses(
  familyId: string,
  yearMonth: string,
  categoryId?: string,
  page?: number,
  perPage?: number
): Promise<ExpenseListResponse> {
  const params = new URLSearchParams({ year_month: yearMonth })
  if (categoryId) params.set('category_id', categoryId)
  if (page != null) params.set('page', String(page))
  if (perPage != null) params.set('per_page', String(perPage))

  const response = await apiClient(`/api/families/${familyId}/expenses?${params.toString()}`)
  if (!response.ok) {
    throw new Error('Failed to fetch expenses')
  }
  return response.json() as Promise<ExpenseListResponse>
}

export async function createExpense(familyId: string, data: ExpenseCreate): Promise<Expense> {
  const response = await apiClient(`/api/families/${familyId}/expenses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to create expense')
  }
  return response.json() as Promise<Expense>
}

export async function getExpense(familyId: string, expenseId: string): Promise<Expense> {
  const response = await apiClient(`/api/families/${familyId}/expenses/${expenseId}`)
  if (!response.ok) {
    throw new Error('Failed to fetch expense')
  }
  return response.json() as Promise<Expense>
}

export async function updateExpense(
  familyId: string,
  expenseId: string,
  data: ExpenseUpdate
): Promise<Expense> {
  const response = await apiClient(`/api/families/${familyId}/expenses/${expenseId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const status = response.status
    if (status === 409) {
      throw new Error('CONFLICT')
    }
    throw new Error('Failed to update expense')
  }
  return response.json() as Promise<Expense>
}

export async function deleteExpense(familyId: string, expenseId: string): Promise<void> {
  const response = await apiClient(`/api/families/${familyId}/expenses/${expenseId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete expense')
  }
}

export async function getBudgetSummary(
  familyId: string,
  month: string
): Promise<BudgetSummaryResponse> {
  const response = await apiClient(
    `/api/families/${familyId}/budget/summary?month=${encodeURIComponent(month)}`
  )
  if (!response.ok) {
    throw new Error('Failed to fetch budget summary')
  }
  return response.json() as Promise<BudgetSummaryResponse>
}
