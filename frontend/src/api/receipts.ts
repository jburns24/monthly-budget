import { apiClient } from './client'
import type { Receipt, ReceiptUploadResponse } from '../types/receipts'

export interface ReceiptListParams {
  status?: string
  uploaded_by?: string
  date_from?: string
  date_to?: string
  page?: number
  per_page?: number
}

export async function uploadReceipt(familyId: string, file: File): Promise<ReceiptUploadResponse> {
  const form = new FormData()
  form.append('file', file)

  // No explicit Content-Type — browser sets multipart/form-data boundary automatically
  const response = await apiClient(`/api/families/${familyId}/receipts`, {
    method: 'POST',
    body: form,
  })
  if (!response.ok) {
    throw new Error(String(response.status))
  }
  return response.json() as Promise<ReceiptUploadResponse>
}

export async function getReceipts(
  familyId: string,
  params?: ReceiptListParams
): Promise<Receipt[]> {
  const query = new URLSearchParams()
  if (params?.status) query.set('status', params.status)
  if (params?.uploaded_by) query.set('uploaded_by', params.uploaded_by)
  if (params?.date_from) query.set('date_from', params.date_from)
  if (params?.date_to) query.set('date_to', params.date_to)
  if (params?.page != null) query.set('page', String(params.page))
  if (params?.per_page != null) query.set('per_page', String(params.per_page))

  const qs = query.toString()
  const response = await apiClient(`/api/families/${familyId}/receipts${qs ? `?${qs}` : ''}`)
  if (!response.ok) {
    throw new Error('Failed to fetch receipts')
  }
  return response.json() as Promise<Receipt[]>
}

export async function getReceipt(familyId: string, receiptId: string): Promise<Receipt> {
  const response = await apiClient(`/api/families/${familyId}/receipts/${receiptId}`)
  if (!response.ok) {
    throw new Error('Failed to fetch receipt')
  }
  return response.json() as Promise<Receipt>
}

export async function deleteReceipt(familyId: string, receiptId: string): Promise<void> {
  const response = await apiClient(`/api/families/${familyId}/receipts/${receiptId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error('Failed to delete receipt')
  }
}

export async function retryReceipt(
  familyId: string,
  receiptId: string
): Promise<ReceiptUploadResponse> {
  const response = await apiClient(`/api/families/${familyId}/receipts/${receiptId}/retry`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error(String(response.status))
  }
  return response.json() as Promise<ReceiptUploadResponse>
}
