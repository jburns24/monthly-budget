import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import CreateExpenseDialog from '../components/expenses/CreateExpenseDialog'
import system from '../theme'

// Mock expenses API to prevent real HTTP calls
vi.mock('../api/expenses', () => ({
  createExpense: vi.fn(() => new Promise(() => {})),
  getExpenses: vi.fn(() => new Promise(() => {})),
  updateExpense: vi.fn(() => new Promise(() => {})),
  deleteExpense: vi.fn(() => new Promise(() => {})),
  getBudgetSummary: vi.fn(() => new Promise(() => {})),
}))

// Mock categories API to prevent real HTTP calls
vi.mock('../api/categories', () => ({
  getCategories: vi.fn(() => new Promise(() => {})),
  createCategory: vi.fn(() => new Promise(() => {})),
  updateCategory: vi.fn(() => new Promise(() => {})),
  deleteCategory: vi.fn(() => new Promise(() => {})),
  seedCategories: vi.fn(() => new Promise(() => {})),
}))

// Mock the toaster to avoid rendering issues in tests
vi.mock('../components/ui/toaster', () => ({
  toaster: {
    create: vi.fn(),
  },
  Toaster: vi.fn(() => null),
}))

import { createExpense } from '../api/expenses'
import { getCategories } from '../api/categories'

// Polyfill localStorage for happy-dom environment
const localStorageMock = (() => {
  let store: Record<string, string> = {}
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value
    },
    removeItem: (key: string) => {
      delete store[key]
    },
    clear: () => {
      store = {}
    },
  }
})()

Object.defineProperty(globalThis, 'localStorage', {
  value: localStorageMock,
  writable: true,
})

const FAMILY_ID = 'fam-123'

const sampleCategories = [
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

function makeExpense(overrides = {}) {
  return {
    id: 'exp-1',
    family_id: FAMILY_ID,
    category: { id: 'cat-1', name: 'Groceries', icon: '🛒' },
    created_by_user: { id: 'user-1', display_name: 'Alice' },
    amount_cents: 4523,
    description: 'Weekly groceries',
    expense_date: '2026-04-01',
    created_at: '2026-04-01T10:00:00Z',
    updated_at: '2026-04-01T10:00:00Z',
    ...overrides,
  }
}

function renderCreateDialog(open = true, onOpenChange = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <CreateExpenseDialog open={open} onOpenChange={onOpenChange} familyId={FAMILY_ID} />
      </QueryClientProvider>
    </ChakraProvider>
  )
}

describe('CreateExpenseDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorageMock.clear()
  })

  it('renders dialog with all required fields when open', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCreateDialog()

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByTestId('expense-amount-input')).toBeInTheDocument()
    expect(screen.getByTestId('expense-description-input')).toBeInTheDocument()
    expect(screen.getByTestId('expense-category-select')).toBeInTheDocument()
    expect(screen.getByTestId('expense-date-input')).toBeInTheDocument()
    expect(screen.getByTestId('expense-submit-btn')).toBeInTheDocument()
  })

  it('does not render dialog when closed', () => {
    renderCreateDialog(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('amount field has inputMode="decimal"', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCreateDialog()

    await waitFor(() => {
      expect(screen.getByTestId('expense-amount-input')).toBeInTheDocument()
    })

    const amountInput = screen.getByTestId('expense-amount-input')
    expect(amountInput).toHaveAttribute('inputmode', 'decimal')
  })

  it('date field defaults to today', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCreateDialog()

    await waitFor(() => {
      expect(screen.getByTestId('expense-date-input')).toBeInTheDocument()
    })

    // Build today string in same format as component
    const now = new Date()
    const year = now.getFullYear()
    const month = String(now.getMonth() + 1).padStart(2, '0')
    const day = String(now.getDate()).padStart(2, '0')
    const todayStr = `${year}-${month}-${day}`

    const dateInput = screen.getByTestId('expense-date-input') as HTMLInputElement
    expect(dateInput.value).toBe(todayStr)
  })

  it('category dropdown populates from categories API', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCreateDialog()

    await waitFor(() => {
      const select = screen.getByTestId('expense-category-select')
      const options = Array.from(select.querySelectorAll('option'))
      const names = options.map((o) => o.textContent ?? '')
      expect(names.some((t) => t.includes('Groceries'))).toBe(true)
      expect(names.some((t) => t.includes('Transport'))).toBe(true)
    })
  })

  it('submit button is disabled when amount is empty', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCreateDialog()

    await waitFor(() => {
      expect(screen.getByTestId('expense-submit-btn')).toBeInTheDocument()
    })

    const submitBtn = screen.getByTestId('expense-submit-btn')
    expect(submitBtn).toBeDisabled()
  })

  it('submit button is enabled when valid amount and category are set', async () => {
    const user = userEvent.setup()
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCreateDialog()

    await waitFor(() => {
      expect(screen.getByTestId('expense-amount-input')).toBeInTheDocument()
    })

    // Wait for categories to load first
    await waitFor(() => {
      const select = screen.getByTestId('expense-category-select')
      const options = Array.from(select.querySelectorAll('option'))
      expect(options.length).toBeGreaterThan(0)
    })

    await user.type(screen.getByTestId('expense-amount-input'), '12.50')

    await waitFor(() => {
      expect(screen.getByTestId('expense-submit-btn')).not.toBeDisabled()
    })
  })

  it('submit calls createExpense with amount converted to cents', async () => {
    const user = userEvent.setup()
    const mockExpense = makeExpense({ amount_cents: 1250 })
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(createExpense).mockResolvedValue(mockExpense)

    renderCreateDialog()

    await waitFor(() => {
      expect(screen.getByTestId('expense-amount-input')).toBeInTheDocument()
    })

    // Wait for categories to load
    await waitFor(() => {
      const select = screen.getByTestId('expense-category-select')
      const options = Array.from(select.querySelectorAll('option'))
      expect(options.length).toBeGreaterThan(0)
    })

    // Type amount - this is the key requirement (cents conversion)
    await user.type(screen.getByTestId('expense-amount-input'), '12.50')

    await waitFor(() => {
      expect(screen.getByTestId('expense-submit-btn')).not.toBeDisabled()
    })

    await user.click(screen.getByTestId('expense-submit-btn'))

    await waitFor(() => {
      expect(createExpense).toHaveBeenCalledWith(
        FAMILY_ID,
        expect.objectContaining({
          amount_cents: 1250,
        })
      )
    })
  })

  it('on success, invalidates expenses and budget-summary queries', async () => {
    const user = userEvent.setup()
    const mockExpense = makeExpense()
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(createExpense).mockResolvedValue(mockExpense)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    render(
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <CreateExpenseDialog open={true} onOpenChange={vi.fn()} familyId={FAMILY_ID} />
        </QueryClientProvider>
      </ChakraProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('expense-amount-input')).toBeInTheDocument()
    })

    // Wait for categories to load
    await waitFor(() => {
      const select = screen.getByTestId('expense-category-select')
      const options = Array.from(select.querySelectorAll('option'))
      expect(options.length).toBeGreaterThan(0)
    })

    await user.type(screen.getByTestId('expense-amount-input'), '45.00')

    await waitFor(() => {
      expect(screen.getByTestId('expense-submit-btn')).not.toBeDisabled()
    })

    await user.click(screen.getByTestId('expense-submit-btn'))

    await waitFor(() => {
      const calls = invalidateSpy.mock.calls
      const expensesInvalidated = calls.some(
        (call) =>
          Array.isArray((call[0] as { queryKey?: unknown[] }).queryKey) &&
          (call[0] as { queryKey?: unknown[] }).queryKey?.[0] === 'expenses'
      )
      const budgetInvalidated = calls.some(
        (call) =>
          Array.isArray((call[0] as { queryKey?: unknown[] }).queryKey) &&
          (call[0] as { queryKey?: unknown[] }).queryKey?.[0] === 'budget-summary'
      )
      expect(expensesInvalidated).toBe(true)
      expect(budgetInvalidated).toBe(true)
    })
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCreateDialog(true, onOpenChange)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
