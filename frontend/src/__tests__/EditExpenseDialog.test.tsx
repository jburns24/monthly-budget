import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import EditExpenseDialog from '../components/expenses/EditExpenseDialog'
import type { Expense } from '../types/expenses'
import system from '../theme'

// Mock expenses API to prevent real HTTP calls
vi.mock('../api/expenses', () => ({
  updateExpense: vi.fn(() => new Promise(() => {})),
  createExpense: vi.fn(() => new Promise(() => {})),
  deleteExpense: vi.fn(() => new Promise(() => {})),
  getExpenses: vi.fn(() => new Promise(() => {})),
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

vi.mock('../api/recurring', () => ({
  createRecurringExpense: vi.fn(() => new Promise(() => {})),
}))

// Mock the toaster to avoid rendering issues in tests
vi.mock('../components/ui/toaster', () => ({
  toaster: {
    create: vi.fn(),
  },
  Toaster: vi.fn(() => null),
}))

import { deleteExpense, updateExpense } from '../api/expenses'
import { createRecurringExpense } from '../api/recurring'
import { getCategories } from '../api/categories'
import { toaster } from '../components/ui/toaster'

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
    receipt_id: null,
    receipt_status: null,
    entry_type: 'expense' as const,
    is_starting_balance: false,
    ...overrides,
  }
}

function renderEditDialog(
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
          <EditExpenseDialog
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

describe('EditExpenseDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders dialog when open with an expense', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderEditDialog()

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByText(/edit expense/i)).toBeInTheDocument()
  })

  it('does not render dialog when closed', () => {
    renderEditDialog(makeExpense(), false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('pre-populates amount field with expense amount in dollars', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    const expense = makeExpense({ amount_cents: 4523 })

    renderEditDialog(expense)

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
    })

    const amountInput = screen.getByTestId('edit-expense-amount') as HTMLInputElement
    // 4523 cents = 45.23
    expect(amountInput.value).toBe('45.23')
  })

  it('pre-populates description field with expense description', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    const expense = makeExpense({ description: 'Weekly groceries' })

    renderEditDialog(expense)

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-description')).toBeInTheDocument()
    })

    const descInput = screen.getByTestId('edit-expense-description') as HTMLInputElement
    expect(descInput.value).toBe('Weekly groceries')
  })

  it('pre-populates date field with expense date', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    const expense = makeExpense({ expense_date: '2026-04-01' })

    renderEditDialog(expense)

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-date')).toBeInTheDocument()
    })

    const dateInput = screen.getByTestId('edit-expense-date') as HTMLInputElement
    expect(dateInput.value).toBe('2026-04-01')
  })

  it('amount field has inputMode="decimal"', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderEditDialog()

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
    })

    const amountInput = screen.getByTestId('edit-expense-amount')
    expect(amountInput).toHaveAttribute('inputmode', 'decimal')
  })

  it('category dropdown populates from categories API', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderEditDialog()

    await waitFor(() => {
      const select = screen.getByTestId('edit-expense-category')
      const options = Array.from(select.querySelectorAll('option'))
      const names = options.map((o) => o.textContent ?? '')
      expect(names.some((t) => t.includes('Groceries'))).toBe(true)
      expect(names.some((t) => t.includes('Transport'))).toBe(true)
    })
  })

  it('pre-selects the current category in the dropdown', async () => {
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    const expense = makeExpense({ category: { id: 'cat-2', name: 'Transport', icon: '🚗' } })

    renderEditDialog(expense)

    await waitFor(() => {
      const select = screen.getByTestId('edit-expense-category') as HTMLSelectElement
      const options = Array.from(select.querySelectorAll('option'))
      expect(options.length).toBeGreaterThan(0)
    })

    const select = screen.getByTestId('edit-expense-category') as HTMLSelectElement
    expect(select.value).toBe('cat-2')
  })

  it('submit calls updateExpense with correct data', async () => {
    const user = userEvent.setup()
    const expense = makeExpense({ amount_cents: 4523, description: 'Weekly groceries' })
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(updateExpense).mockResolvedValue({
      ...expense,
      amount_cents: 5000,
      description: 'Updated groceries',
    })

    renderEditDialog(expense)

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
    })

    const amountInput = screen.getByTestId('edit-expense-amount')
    await user.clear(amountInput)
    await user.type(amountInput, '50.00')

    const descInput = screen.getByTestId('edit-expense-description')
    await user.clear(descInput)
    await user.type(descInput, 'Updated groceries')

    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(updateExpense).toHaveBeenCalledWith(
        FAMILY_ID,
        expense.id,
        expect.objectContaining({
          amount_cents: 5000,
          description: 'Updated groceries',
          expected_updated_at: expense.updated_at,
        })
      )
    })
  })

  it('on success, invalidates expenses and budget-summary queries', async () => {
    const user = userEvent.setup()
    const expense = makeExpense()
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(updateExpense).mockResolvedValue(expense)

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    render(
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <EditExpenseDialog
            open={true}
            onOpenChange={vi.fn()}
            familyId={FAMILY_ID}
            expense={expense}
          />
        </QueryClientProvider>
      </ChakraProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /save/i }))

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

  it('shows conflict toast when updateExpense throws CONFLICT error', async () => {
    const user = userEvent.setup()
    const expense = makeExpense()
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(updateExpense).mockRejectedValue(new Error('CONFLICT'))

    renderEditDialog(expense)

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(toaster.create).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'error',
          title: expect.stringMatching(/modified by someone else/i),
        })
      )
    })
  })

  it('shows generic error toast on non-conflict update failure', async () => {
    const user = userEvent.setup()
    const expense = makeExpense()
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)
    vi.mocked(updateExpense).mockRejectedValue(new Error('Network error'))

    renderEditDialog(expense)

    await waitFor(() => {
      expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /save/i }))

    await waitFor(() => {
      expect(toaster.create).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'error',
          title: 'Error',
        })
      )
    })
  })

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderEditDialog(makeExpense(), true, onOpenChange)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /cancel/i }))

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  describe('repeat', () => {
    it('hides the recurring fields until Repeat is checked', async () => {
      const user = userEvent.setup()
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      renderEditDialog()

      const checkbox = await screen.findByTestId('repeat-checkbox')
      expect(checkbox).not.toBeChecked()
      expect(screen.queryByTestId('repeat-frequency-select')).not.toBeInTheDocument()

      await user.click(checkbox)
      expect(screen.getByTestId('repeat-frequency-select')).toBeInTheDocument()
    })

    it('saves the expense then creates a rule starting at the next occurrence', async () => {
      const user = userEvent.setup()
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      vi.mocked(updateExpense).mockResolvedValue(makeExpense())
      vi.mocked(createRecurringExpense).mockResolvedValue({} as never)
      const onOpenChange = vi.fn()
      renderEditDialog(makeExpense({ expense_date: '2026-01-31' }), true, onOpenChange)

      await user.click(await screen.findByTestId('repeat-checkbox'))
      await user.click(screen.getByRole('button', { name: /^save$/i }))

      await waitFor(() => expect(createRecurringExpense).toHaveBeenCalledTimes(1))
      expect(updateExpense).toHaveBeenCalledTimes(1)
      expect(createRecurringExpense).toHaveBeenCalledWith(
        FAMILY_ID,
        expect.objectContaining({
          amount_cents: 4523,
          description: 'Weekly groceries',
          entry_type: 'expense',
          frequency: 'monthly',
          start_date: '2026-02-28',
          end_date: null,
          category_id: 'cat-1',
        })
      )
      await waitFor(() =>
        expect(toaster.create).toHaveBeenCalledWith(
          expect.objectContaining({ title: 'Expense updated and set to repeat' })
        )
      )
      expect(onOpenChange).toHaveBeenCalledWith(false)
    })

    it('does not create a rule when Repeat is unchecked', async () => {
      const user = userEvent.setup()
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      vi.mocked(updateExpense).mockResolvedValue(makeExpense())
      renderEditDialog()

      await screen.findByTestId('repeat-checkbox')
      await user.click(screen.getByRole('button', { name: /^save$/i }))

      await waitFor(() => expect(updateExpense).toHaveBeenCalledTimes(1))
      expect(createRecurringExpense).not.toHaveBeenCalled()
    })

    it('shows the checkbox locked on for entries that belong to a recurring rule', async () => {
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      renderEditDialog(makeExpense({ recurring_expense_id: 'rule-1' }))

      const checkbox = await screen.findByTestId('repeat-checkbox')
      expect(checkbox).toBeChecked()
      expect(checkbox).toBeDisabled()
      expect(screen.getByTestId('repeat-locked-hint')).toBeInTheDocument()
      expect(screen.queryByTestId('repeat-frequency-select')).not.toBeInTheDocument()
    })

    it('blocks save when the end date is before the first repeat', async () => {
      const user = userEvent.setup()
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      renderEditDialog(makeExpense({ expense_date: '2026-04-01' }))

      await user.click(await screen.findByTestId('repeat-checkbox'))
      fireEvent.change(screen.getByTestId('repeat-end-input'), { target: { value: '2026-04-15' } })

      expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled()
    })
  })

  describe('delete', () => {
    async function openConfirm() {
      const user = userEvent.setup()
      const onOpenChange = vi.fn()
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      renderEditDialog(makeExpense(), true, onOpenChange)
      await user.click(await screen.findByTestId('edit-expense-delete'))
      return { user, onOpenChange }
    }

    it('asks for confirmation before deleting', async () => {
      await openConfirm()

      expect(screen.getByText(/can't be undone/i)).toBeInTheDocument()
      expect(deleteExpense).not.toHaveBeenCalled()
    })

    it('deletes, toasts and closes on confirm', async () => {
      vi.mocked(deleteExpense).mockResolvedValue(undefined)
      const { user, onOpenChange } = await openConfirm()

      await user.click(screen.getByTestId('delete-expense-confirm'))

      await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
      expect(deleteExpense).toHaveBeenCalledWith(FAMILY_ID, makeExpense().id)
      expect(toaster.create).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Expense deleted' })
      )
    })

    it('does not delete when the confirmation is dismissed', async () => {
      const { user } = await openConfirm()

      await user.click(screen.getByRole('button', { name: /keep/i }))

      expect(deleteExpense).not.toHaveBeenCalled()
      expect(screen.getByTestId('edit-expense-delete')).toBeInTheDocument()
    })

    it('shows an error toast when delete fails', async () => {
      vi.mocked(deleteExpense).mockRejectedValue(new Error('boom'))
      const { user, onOpenChange } = await openConfirm()

      await user.click(screen.getByTestId('delete-expense-confirm'))

      await waitFor(() =>
        expect(toaster.create).toHaveBeenCalledWith(expect.objectContaining({ type: 'error' }))
      )
      expect(onOpenChange).not.toHaveBeenCalled()
    })
  })

  describe('entry type', () => {
    it('defaults toggle from expense.entry_type and hides category for income', async () => {
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      const expense = makeExpense({
        entry_type: 'income',
        category: null,
        description: 'Paycheck',
      })

      renderEditDialog(expense)

      await waitFor(() => {
        expect(
          within(screen.getByTestId('entry-type-toggle')).getByRole('radio', { name: /^income$/i })
        ).toBeChecked()
      })

      expect(screen.queryByTestId('edit-expense-category')).not.toBeInTheDocument()
      expect(screen.getByRole('heading', { name: /edit income/i })).toBeInTheDocument()
    })

    it('hides category when switching an expense to income', async () => {
      const user = userEvent.setup()
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)

      renderEditDialog()

      await waitFor(() => {
        expect(screen.getByTestId('edit-expense-category')).toBeInTheDocument()
      })

      await user.click(within(screen.getByTestId('entry-type-toggle')).getByText('Income'))

      expect(screen.queryByTestId('edit-expense-category')).not.toBeInTheDocument()
    })

    it('submits income update with entry_type and without category_id', async () => {
      const user = userEvent.setup()
      const expense = makeExpense({ entry_type: 'expense' })
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      vi.mocked(updateExpense).mockResolvedValue({
        ...expense,
        entry_type: 'income',
        category: null,
      })

      renderEditDialog(expense)

      await waitFor(() => {
        expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
      })

      await user.click(within(screen.getByTestId('entry-type-toggle')).getByText('Income'))
      await waitFor(() => {
        expect(screen.queryByTestId('edit-expense-category')).not.toBeInTheDocument()
      })
      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(updateExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          expense.id,
          expect.objectContaining({
            entry_type: 'income',
            expected_updated_at: expense.updated_at,
          })
        )
      })

      const payload = vi.mocked(updateExpense).mock.calls[0][2]
      expect(payload).not.toHaveProperty('category_id')
    })

    it('shows Income updated toast when saving an income entry', async () => {
      const user = userEvent.setup()
      const expense = makeExpense({ entry_type: 'income', category: null })
      vi.mocked(getCategories).mockResolvedValue(sampleCategories)
      vi.mocked(updateExpense).mockResolvedValue(expense)

      renderEditDialog(expense)

      await waitFor(() => {
        expect(screen.getByTestId('edit-expense-amount')).toBeInTheDocument()
      })

      await user.click(screen.getByRole('button', { name: /save/i }))

      await waitFor(() => {
        expect(toaster.create).toHaveBeenCalledWith(
          expect.objectContaining({
            title: 'Income updated',
            type: 'success',
          })
        )
      })
    })
  })
})
