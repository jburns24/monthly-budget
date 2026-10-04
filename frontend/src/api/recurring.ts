import { apiClient } from './client'
import type {
  RecurringExpense,
  RecurringExpenseCreate,
  RecurringExpenseListResponse,
  RecurringExpenseUpdate,
} from '../types/recurring'

export async function getRecurringExpenses(familyId: string): Promise<RecurringExpense[]> {
  const response = await apiClient(`/api/families/${familyId}/recurring-expenses`)
  if (!response.ok) {
    throw new Error('Failed to fetch recurring expenses')
  }
  const data = (await response.json()) as RecurringExpenseListResponse
  return data.recurring_expenses
}

export async function createRecurringExpense(
  familyId: string,
  data: RecurringExpenseCreate
): Promise<RecurringExpense> {
  const response = await apiClient(`/api/families/${familyId}/recurring-expenses`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to create recurring expense')
  }
  return response.json() as Promise<RecurringExpense>
}

export async function updateRecurringExpense(
  familyId: string,
  ruleId: string,
  data: RecurringExpenseUpdate
): Promise<RecurringExpense> {
  const response = await apiClient(`/api/families/${familyId}/recurring-expenses/${ruleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to update recurring expense')
  }
  return response.json() as Promise<RecurringExpense>
}

export async function deleteRecurringExpense(familyId: string, ruleId: string): Promise<void> {
  const response = await apiClient(`/api/families/${familyId}/recurring-expenses/${ruleId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete recurring expense')
  }
}
