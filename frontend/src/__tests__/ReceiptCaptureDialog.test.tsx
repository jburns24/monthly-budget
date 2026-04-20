import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import ReceiptCaptureDialog from '../components/expenses/ReceiptCaptureDialog'
import system from '../theme'
import type { Category } from '../types/categories'
import type { ReceiptUploadResponse } from '../types/receipts'

vi.mock('../api/receipts', () => ({
  uploadReceipt: vi.fn(() => new Promise(() => {})),
  getReceipts: vi.fn(() => new Promise(() => {})),
  getReceipt: vi.fn(() => new Promise(() => {})),
  deleteReceipt: vi.fn(() => new Promise(() => {})),
  retryReceipt: vi.fn(() => new Promise(() => {})),
}))

vi.mock('../api/categories', () => ({
  getCategories: vi.fn(() => new Promise(() => {})),
  createCategory: vi.fn(() => new Promise(() => {})),
  updateCategory: vi.fn(() => new Promise(() => {})),
  deleteCategory: vi.fn(() => new Promise(() => {})),
  seedCategories: vi.fn(() => new Promise(() => {})),
}))

vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

vi.mock('browser-image-compression', () => ({
  default: vi.fn(async (file: File) => file),
}))

import { uploadReceipt } from '../api/receipts'
import { getCategories } from '../api/categories'
import { toaster } from '../components/ui/toaster'

const FAMILY_ID = 'fam-123'

const sampleCategories: Category[] = [
  {
    id: 'cat-1',
    family_id: FAMILY_ID,
    name: 'Groceries',
    icon: '🛒',
    sort_order: 1,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'cat-2',
    family_id: FAMILY_ID,
    name: 'Transport',
    icon: '🚗',
    sort_order: 2,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
]

function makeUploadResponse(overrides: Partial<ReceiptUploadResponse> = {}): ReceiptUploadResponse {
  return {
    receipt: {
      id: 'rcpt-1',
      family_id: FAMILY_ID,
      uploaded_by: 'user-1',
      image_path: '/receipts/rcpt-1.jpg',
      raw_response: null,
      parsed_date: '2026-04-19',
      parsed_total_cents: 4523,
      parsed_merchant: 'Whole Foods',
      status: 'completed',
      error_message: null,
      created_at: '2026-04-19T10:00:00Z',
    },
    expense_id: 'exp-1',
    needs_edit: false,
    ...overrides,
  }
}

function renderDialog(open = true, onOpenChange = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    ...render(
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <ReceiptCaptureDialog open={open} onOpenChange={onOpenChange} familyId={FAMILY_ID} />
        </QueryClientProvider>
      </ChakraProvider>
    ),
  }
}

async function reachPreview() {
  await waitFor(() => expect(screen.getByTestId('receipt-capture-dialog')).toBeInTheDocument())
  const file = new File(['img-data'], 'receipt.jpg', { type: 'image/jpeg' })
  const input = screen.getByTestId('receipt-file-input')
  await userEvent.upload(input, file)
  await waitFor(() => expect(screen.getByTestId('receipt-preview-image')).toBeInTheDocument())
}

async function reachReviewing(response = makeUploadResponse()) {
  vi.mocked(uploadReceipt).mockResolvedValueOnce(response)
  await reachPreview()
  await userEvent.click(screen.getByTestId('receipt-upload-btn'))
  await waitFor(() => expect(screen.getByTestId('receipt-reviewing')).toBeInTheDocument())
}

beforeEach(() => {
  vi.clearAllMocks()
  globalThis.URL.createObjectURL = vi.fn(() => 'blob:fake-url')
  globalThis.URL.revokeObjectURL = vi.fn()
})

describe('idle phase', () => {
  it('renders dialog when open', async () => {
    renderDialog()
    await waitFor(() => expect(screen.getByTestId('receipt-capture-dialog')).toBeInTheDocument())
  })

  it('does not render dialog when closed', () => {
    renderDialog(false)
    expect(screen.queryByTestId('receipt-capture-dialog')).not.toBeInTheDocument()
  })

  it('shows dropzone with instructions', async () => {
    renderDialog()
    await waitFor(() => expect(screen.getByTestId('receipt-dropzone')).toBeInTheDocument())
    expect(screen.getByText(/drag & drop a receipt image/i)).toBeInTheDocument()
  })

  it('file input has capture="environment"', async () => {
    renderDialog()
    await waitFor(() => expect(screen.getByTestId('receipt-file-input')).toBeInTheDocument())
    expect(screen.getByTestId('receipt-file-input')).toHaveAttribute('capture', 'environment')
  })

  it('shows Cancel button', async () => {
    renderDialog()
    await waitFor(() => expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument())
  })
})

describe('preview phase', () => {
  it('shows preview image after file selected', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachPreview()
    expect(screen.getByTestId('receipt-preview-image')).toBeInTheDocument()
  })

  it('shows file name', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachPreview()
    expect(screen.getByText('receipt.jpg')).toBeInTheDocument()
  })

  it('shows Back and Upload buttons', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachPreview()
    expect(screen.getByTestId('receipt-back-btn')).toBeInTheDocument()
    expect(screen.getByTestId('receipt-upload-btn')).toBeInTheDocument()
  })

  it('Back button returns to idle phase', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachPreview()
    await userEvent.click(screen.getByTestId('receipt-back-btn'))
    await waitFor(() => expect(screen.getByTestId('receipt-dropzone')).toBeInTheDocument())
  })
})

describe('uploading phase', () => {
  it('shows spinner after Upload clicked', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(uploadReceipt).mockReturnValue(new Promise(() => {}))
    renderDialog()
    await reachPreview()
    await userEvent.click(screen.getByTestId('receipt-upload-btn'))
    await waitFor(() => expect(screen.getByTestId('receipt-uploading')).toBeInTheDocument())
  })

  it('returns to preview and shows error toast on upload failure', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(uploadReceipt).mockRejectedValueOnce(new Error('500'))
    renderDialog()
    await reachPreview()
    await userEvent.click(screen.getByTestId('receipt-upload-btn'))
    await waitFor(() =>
      expect(toaster.create).toHaveBeenCalledWith(expect.objectContaining({ type: 'error' }))
    )
    await waitFor(() => expect(screen.getByTestId('receipt-preview-image')).toBeInTheDocument())
  })

  it('maps 422 error to "not a receipt" description', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(uploadReceipt).mockRejectedValueOnce(new Error('422'))
    renderDialog()
    await reachPreview()
    await userEvent.click(screen.getByTestId('receipt-upload-btn'))
    await waitFor(() =>
      expect(toaster.create).toHaveBeenCalledWith(
        expect.objectContaining({
          description: expect.stringMatching(/doesn't look like a receipt/i),
        })
      )
    )
  })
})

describe('reviewing phase', () => {
  it('shows merchant and amount from upload response', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachReviewing()
    expect(screen.getByTestId('receipt-merchant')).toHaveTextContent('Whole Foods')
    expect(screen.getByTestId('receipt-amount')).toHaveTextContent('$45.23')
  })

  it('formats null amount and merchant as dash', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    const response = makeUploadResponse()
    response.receipt.parsed_total_cents = null
    response.receipt.parsed_merchant = null
    await reachReviewing(response)
    expect(screen.getByTestId('receipt-amount')).toHaveTextContent('—')
    expect(screen.getByTestId('receipt-merchant')).toHaveTextContent('—')
  })

  it('shows needs-review badge when needs_edit is true', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachReviewing(makeUploadResponse({ needs_edit: true }))
    expect(screen.getByTestId('receipt-needs-review-badge')).toBeInTheDocument()
  })

  it('does not show needs-review badge when needs_edit is false', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachReviewing(makeUploadResponse({ needs_edit: false }))
    expect(screen.queryByTestId('receipt-needs-review-badge')).not.toBeInTheDocument()
  })

  it('populates category select from categories API', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachReviewing()
    await waitFor(() => {
      const select = screen.getByTestId('receipt-category-select')
      const options = Array.from(select.querySelectorAll('option'))
      expect(options.some((o) => o.textContent?.includes('Groceries'))).toBe(true)
      expect(options.some((o) => o.textContent?.includes('Transport'))).toBe(true)
    })
  })

  it('shows Confirm and Cancel buttons', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachReviewing()
    expect(screen.getByTestId('receipt-confirm-btn')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('invalidates expenses, budget-summary, and receipts queries on upload success', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    render(
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <ReceiptCaptureDialog open={true} onOpenChange={vi.fn()} familyId={FAMILY_ID} />
        </QueryClientProvider>
      </ChakraProvider>
    )
    await reachReviewing()
    await waitFor(() => {
      const keys = invalidateSpy.mock.calls.map(
        (c) => (c[0] as { queryKey?: unknown[] }).queryKey?.[0]
      )
      expect(keys).toContain('expenses')
      expect(keys).toContain('budget-summary')
      expect(keys).toContain('receipts')
    })
  })
})

describe('responsive placement', () => {
  it('passes responsive placement (bottom on mobile, center on md+) to DialogRoot', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    const chakra = await import('@chakra-ui/react')
    const DialogRootSpy = vi.spyOn(chakra, 'DialogRoot')
    renderDialog()
    await waitFor(() => expect(screen.getByTestId('receipt-capture-dialog')).toBeInTheDocument())
    // Locate the call whose placement prop is the responsive object.
    const responsiveCall = DialogRootSpy.mock.calls
      .map(([props]) => props as { placement?: unknown } | null)
      .find(
        (p) =>
          p != null &&
          typeof p.placement === 'object' &&
          p.placement !== null &&
          'base' in (p.placement as object)
      )
    expect(responsiveCall).toBeDefined()
    expect(responsiveCall!.placement).toEqual({ base: 'bottom', md: 'center' })
    DialogRootSpy.mockRestore()
  })
})

describe('done phase', () => {
  it('shows success message after Confirm clicked', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachReviewing()
    await userEvent.click(screen.getByTestId('receipt-confirm-btn'))
    await waitFor(() => expect(screen.getByTestId('receipt-done')).toBeInTheDocument())
    expect(screen.getByText(/receipt added successfully/i)).toBeInTheDocument()
  })

  it('shows Close button in done phase', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    renderDialog()
    await reachReviewing()
    await userEvent.click(screen.getByTestId('receipt-confirm-btn'))
    await waitFor(() => expect(screen.getByTestId('receipt-close-btn')).toBeInTheDocument())
  })

  it('Close button calls onOpenChange(false)', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    const onOpenChange = vi.fn()
    render(
      <ChakraProvider value={system}>
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <ReceiptCaptureDialog open={true} onOpenChange={onOpenChange} familyId={FAMILY_ID} />
        </QueryClientProvider>
      </ChakraProvider>
    )
    await reachReviewing()
    await userEvent.click(screen.getByTestId('receipt-confirm-btn'))
    await waitFor(() => expect(screen.getByTestId('receipt-close-btn')).toBeInTheDocument())
    await userEvent.click(screen.getByTestId('receipt-close-btn'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
