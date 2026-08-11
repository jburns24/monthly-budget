import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import StartingBalancePrompt from '../components/expenses/StartingBalancePrompt'
import system from '../theme'
import type { Expense } from '../types/expenses'

vi.mock('../api/expenses', () => ({
  createExpense: vi.fn(() => new Promise(() => {})),
}))

vi.mock('../components/ui/toaster', () => ({
  toaster: {
    create: vi.fn(),
  },
  Toaster: vi.fn(() => null),
}))

import { createExpense } from '../api/expenses'

const FAMILY_ID = 'fam-123'

function makeIncomeExpense(overrides: Partial<Expense> = {}): Expense {
  return {
    id: 'exp-income-1',
    family_id: FAMILY_ID,
    category: null,
    created_by_user: { id: 'user-1', display_name: 'Alice' },
    amount_cents: 50000,
    description: 'Starting balance',
    expense_date: '2026-03-01',
    created_at: '2026-03-01T10:00:00Z',
    updated_at: '2026-03-01T10:00:00Z',
    receipt_id: null,
    receipt_status: null,
    entry_type: 'income',
    is_starting_balance: true,
    ...overrides,
  }
}

function renderPrompt(
  props: Partial<React.ComponentProps<typeof StartingBalancePrompt>> = {},
  queryClient?: QueryClient
) {
  const client = queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={client}>
        <StartingBalancePrompt
          familyId={FAMILY_ID}
          yearMonth="2026-03"
          hasStartingBalance={false}
          {...props}
        />
      </QueryClientProvider>
    </ChakraProvider>
  )
}

describe('StartingBalancePrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date(2026, 3, 15, 12, 0, 0))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows when hasStartingBalance is false', () => {
    renderPrompt({ hasStartingBalance: false })

    expect(screen.getByTestId('starting-balance-prompt')).toBeInTheDocument()
    expect(screen.getByText(/starting balance/i)).toBeInTheDocument()
  })

  it('hides when hasStartingBalance is true', () => {
    renderPrompt({ hasStartingBalance: true })

    expect(screen.queryByTestId('starting-balance-prompt')).not.toBeInTheDocument()
  })

  it('hides after Skip for now is clicked', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderPrompt({ hasStartingBalance: false })

    await user.click(screen.getByTestId('starting-balance-skip-btn'))

    expect(screen.queryByTestId('starting-balance-prompt')).not.toBeInTheDocument()
  })

  it('submit creates starting-balance income for first of past month', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    vi.mocked(createExpense).mockResolvedValue(makeIncomeExpense())

    renderPrompt({ yearMonth: '2026-03', hasStartingBalance: false })

    await user.type(screen.getByTestId('starting-balance-amount-input'), '500.00')
    await user.click(screen.getByTestId('starting-balance-submit-btn'))

    await waitFor(() => {
      expect(createExpense).toHaveBeenCalledWith(FAMILY_ID, {
        amount_cents: 50000,
        description: 'Starting balance',
        expense_date: '2026-03-01',
        entry_type: 'income',
        is_starting_balance: true,
      })
    })
  })

  it('submit uses today as expense_date when viewing the current month', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    vi.mocked(createExpense).mockResolvedValue(makeIncomeExpense({ expense_date: '2026-04-15' }))

    renderPrompt({ yearMonth: '2026-04', hasStartingBalance: false })

    await user.type(screen.getByTestId('starting-balance-amount-input'), '100')
    await user.click(screen.getByTestId('starting-balance-submit-btn'))

    await waitFor(() => {
      expect(createExpense).toHaveBeenCalledWith(
        FAMILY_ID,
        expect.objectContaining({
          expense_date: '2026-04-15',
          entry_type: 'income',
          is_starting_balance: true,
        })
      )
    })
  })

  it('on success, invalidates budget-summary and expenses queries', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    vi.mocked(createExpense).mockResolvedValue(makeIncomeExpense())

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    renderPrompt({ hasStartingBalance: false, yearMonth: '2026-03' }, queryClient)

    await user.type(screen.getByTestId('starting-balance-amount-input'), '250')
    await user.click(screen.getByTestId('starting-balance-submit-btn'))

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['budget-summary', FAMILY_ID, '2026-03'],
      })
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['expenses', FAMILY_ID],
      })
    })
  })

  it('submit button is disabled when amount is empty or invalid', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    renderPrompt({ hasStartingBalance: false })

    expect(screen.getByTestId('starting-balance-submit-btn')).toBeDisabled()

    await user.type(screen.getByTestId('starting-balance-amount-input'), '0')
    expect(screen.getByTestId('starting-balance-submit-btn')).toBeDisabled()

    await user.clear(screen.getByTestId('starting-balance-amount-input'))
    await user.type(screen.getByTestId('starting-balance-amount-input'), 'abc')
    expect(screen.getByTestId('starting-balance-submit-btn')).toBeDisabled()
  })
})
