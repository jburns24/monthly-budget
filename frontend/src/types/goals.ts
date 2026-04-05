export interface MonthlyGoal {
  id: string
  family_id: string
  category_id: string
  year_month: string
  amount_cents: number
  version: number
  created_at: string
  updated_at: string
}

export interface MonthlyGoalCreate {
  category_id: string
  amount_cents: number
}

export interface MonthlyGoalUpdate {
  amount_cents: number
  expected_version: number
}

export interface BulkGoalsRequest {
  year_month: string
  goals: MonthlyGoalCreate[]
}

export interface BulkGoalsResponse {
  year_month: string
  created: number
  updated: number
  deleted: number
  goals: MonthlyGoal[]
}

export interface GoalsListResponse {
  year_month: string
  goals: MonthlyGoal[]
  has_previous_goals: boolean
}

export interface RolloverRequest {
  source_month: string
  target_month: string
}

export interface RolloverResponse {
  copied_count: number
}
