export interface Category {
  id: string
  family_id: string
  name: string
  icon: string | null
  sort_order: number
  is_active: boolean
  created_at: string
}

export interface CategoryCreate {
  name: string
  icon?: string | null
  sort_order?: number
}

export interface CategoryUpdate {
  name?: string
  icon?: string | null
  sort_order?: number
}

export interface CategoryDeleteResponse {
  message: string
  deleted: boolean
  archived: boolean
  expense_count: number
}

export interface SeedResponse {
  message: string
  created_count: number
}
