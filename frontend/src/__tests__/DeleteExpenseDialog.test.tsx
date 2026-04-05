import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import DeleteExpenseDialog from '../components/expenses/DeleteExpenseDialog'
import type { Expense } from '../types/expenses'
import system from '../theme'

// Mock expenses API to prevent real HTTP calls
vi.mock('../api/expenses', () => ({
  deleteExpense: vi.fn(() => new Promise(() => {})),
  createExpense: vi.fn(() => new Promise(() => {})),
  updateExpense: vi.fn(() => new Promise(() => {})),
  getExpenses: vi.fn(() => new Promise(() => {})),
  getBudgetSummary: vi.fn(() => new Promise(() => {})),
}))

// Mock the toaster to avoid rendering issues in tests
vi.mock('../components/ui/toaster', () => ({
  toaster: {
    create: vi.fn(),
  },
  Toaster: vi.fn(() => null),
}))

import { deleteExpense } from '../api/expenses'
import { toaster } from '../components/ui/toaster'

const FAMILY_ID = 'fam-123'

function makeExpense(overrides: Partial<Expense> = {}): Expense {
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

function renderDeleteDialog(
  expense: Expense | null = makeExpense(),
  open = true,
  onOpenChange = vi.fn()
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    ...render(
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <DeleteExpenseDialog
            open={open}
            onOpenChange={onOpenChange}
            familyId={FAMILY_ID}
            expense={expense}
          />
        </QueryClientProvider>
      </ChakraProvider>
    ),
  }
}

describe('DeleteExpenseDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders dialog when open with an expense', async () => {
    renderDeleteDialog()

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByText(/delete expense/i)).toBeInTheDocument()
  })

  it('does not render dialog when closed', () => {
    renderDeleteDialog(makeExpense(), false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows expense description and formatted amount in confirmation message', async () => {
    const expense = makeExpense({ description: 'Weekly groceries', amount_cents: 4523 })

    renderDeleteDialog(expense)

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByText(/weekly groceries/i)).toBeInTheDocument()
    expect(screen.getByText(/\$45\.23/)).toBeInTheDocument()
  })

  it('shows "(no description)" when expense has no description', async () => {
    const expense = makeExpense({ description: '' })

    renderDeleteDialog(expense)

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByText(/no description/i)).toBeInTheDocument()
  })

  it('shows confirm Delete button', async () => {
    renderDeleteDialog()

    await waitFor(() => {
      expect(screen.getByTestId('delete-expense-confirm')).toBeInTheDocument()
    })
  })

  it('shows Cancel button', async () => {
    renderDeleteDialog()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })
  })

  it('calls deleteExpense with correct ids on confirmation', async () => {
    const user = userEvent.setup()
    const expense = makeExpense({ id: 'exp-42' })
    vi.mocked(deleteExpense).mockResolvedValue(undefined)

    renderDeleteDialog(expense)

    await waitFor(() => {
      expect(screen.getByTestId('delete-expense-confirm')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('delete-expense-confirm'))

    await waitFor(() => {
      expect(deleteExpense).toHaveBeenCalledWith(FAMILY_ID, 'exp-42')
    })
  })

  it('on success, invalidates expenses and budget-summary queries', async () => {
    const user = userEvent.setup()
    const expense = makeExpense()
    vi.mocked(deleteExpense).mockResolvedValue(undefined)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    render(
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <DeleteExpenseDialog
            open={true}
            onOpenChange={vi.fn()}
            familyId={FAMILY_ID}
            expense={expense}
          />
        </QueryClientProvider>
      </ChakraProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('delete-expense-confirm')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('delete-expense-confirm'))

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

  it('shows success toast after deletion', async () => {
    const user = userEvent.setup()
    vi.mocked(deleteExpense).mockResolvedValue(undefined)

    renderDeleteDialog()

    await waitFor(() => {
      expect(screen.getByTestId('delete-expense-confirm')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('delete-expense-confirm'))

    await waitFor(() => {
      expect(toaster.create).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'success',
          title: expect.stringMatching(/expense deleted/i),
        })
      )
    })
  })

  it('shows error toast when deletion fails', async () => {
    const user = userEvent.setup()
    vi.mocked(deleteExpense).mockRejectedValue(new Error('Network error'))

    renderDeleteDialog()

    await waitFor(() => {
      expect(screen.getByTestId('delete-expense-confirm')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('delete-expense-confirm'))

    await waitFor(() => {
      expect(toaster.create).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'error',
        })
      )
    })
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()

    renderDeleteDialog(makeExpense(), true, onOpenChange)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('Delete button is disabled when expense is null', () => {
    renderDeleteDialog(null)

    const deleteBtn = screen.getByTestId('delete-expense-confirm')
    expect(deleteBtn).toBeDisabled()
  })
})
