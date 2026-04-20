export type ReceiptStatus = 'processing' | 'completed' | 'failed'

export interface Receipt {
  id: string
  family_id: string
  uploaded_by: string
  image_path: string | null
  raw_response: Record<string, unknown> | null
  parsed_date: string | null
  parsed_total_cents: number | null
  parsed_merchant: string | null
  status: ReceiptStatus
  error_message: string | null
  created_at: string
}

export interface ReceiptUploadResponse {
  receipt: Receipt
  expense_id: string | null
  needs_edit: boolean
}
