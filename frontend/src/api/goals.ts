import { apiClient } from './client'
import type {
  MonthlyGoal,
  MonthlyGoalUpdate,
  BulkGoalsRequest,
  BulkGoalsResponse,
  GoalsListResponse,
  RolloverRequest,
  RolloverResponse,
} from '../types/goals'

export async function getGoals(familyId: string, yearMonth: string): Promise<GoalsListResponse> {
  const params = new URLSearchParams({ month: yearMonth })
  const response = await apiClient(`/api/families/${familyId}/goals?${params.toString()}`)
  if (!response.ok) {
    throw new Error('Failed to fetch goals')
  }
  return response.json() as Promise<GoalsListResponse>
}

export async function updateGoal(
  familyId: string,
  goalId: string,
  data: MonthlyGoalUpdate
): Promise<MonthlyGoal> {
  const response = await apiClient(`/api/families/${familyId}/goals/${goalId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    if (response.status === 409) {
      throw new Error('CONFLICT')
    }
    throw new Error('Failed to update goal')
  }
  return response.json() as Promise<MonthlyGoal>
}

export async function updateGoalsBulk(
  familyId: string,
  data: BulkGoalsRequest
): Promise<BulkGoalsResponse> {
  const response = await apiClient(`/api/families/${familyId}/goals`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to update goals')
  }
  return response.json() as Promise<BulkGoalsResponse>
}

export async function deleteGoal(familyId: string, goalId: string): Promise<void> {
  const response = await apiClient(`/api/families/${familyId}/goals/${goalId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete goal')
  }
}

export async function rolloverGoals(
  familyId: string,
  data: RolloverRequest
): Promise<RolloverResponse> {
  const response = await apiClient(`/api/families/${familyId}/goals/rollover`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to rollover goals')
  }
  return response.json() as Promise<RolloverResponse>
}
