import { apiClient } from './client'
import type {
  Category,
  CategoryCreate,
  CategoryUpdate,
  CategoryDeleteResponse,
  SeedResponse,
} from '../types/categories'

export async function getCategories(familyId: string): Promise<Category[]> {
  const response = await apiClient(`/api/families/${familyId}/categories`)
  if (!response.ok) {
    throw new Error('Failed to fetch categories')
  }
  return response.json() as Promise<Category[]>
}

export async function createCategory(familyId: string, data: CategoryCreate): Promise<Category> {
  const response = await apiClient(`/api/families/${familyId}/categories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to create category')
  }
  return response.json() as Promise<Category>
}

export async function updateCategory(
  familyId: string,
  categoryId: string,
  data: CategoryUpdate
): Promise<Category> {
  const response = await apiClient(`/api/families/${familyId}/categories/${categoryId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to update category')
  }
  return response.json() as Promise<Category>
}

export async function deleteCategory(
  familyId: string,
  categoryId: string
): Promise<CategoryDeleteResponse> {
  const response = await apiClient(`/api/families/${familyId}/categories/${categoryId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete category')
  }
  return response.json() as Promise<CategoryDeleteResponse>
}

export async function seedCategories(familyId: string): Promise<SeedResponse> {
  const response = await apiClient(`/api/families/${familyId}/categories/seed`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error('Failed to seed categories')
  }
  return response.json() as Promise<SeedResponse>
}
