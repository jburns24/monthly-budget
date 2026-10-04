import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import RecurringPage from '../pages/RecurringPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'
import type { RecurringExpense } from '../types/recurring'

vi.mock('../hooks/useAuth', () => ({ useAuth: vi.fn() }))

vi.mock('../api/recurring', () => ({
  getRecurringExpenses: vi.fn(),
  createRecurringExpense: vi.fn(() => new Promise(() => {})),
  updateRecurringExpense: vi.fn(),
  deleteRecurringExpense: vi.fn(),
}))

vi.mock('../api/categories', () => ({
  getCategories: vi.fn(() => Promise.resolve([{ id: 'cat-1', name: 'Housing', icon: '🏠' }])),
}))

vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

import { useAuth } from '../hooks/useAuth'
import {
  deleteRecurringExpense,
  getRecurringExpenses,
  updateRecurringExpense,
} from '../api/recurring'

const FAMILY_ID = 'fam-123'

function makeRule(overrides: Partial<RecurringExpense> = {}): RecurringExpense {
  return {
    id: 'rule-1',
    family_id: FAMILY_ID,
    category_id: 'cat-1',
    amount_cents: 150000,
    description: 'Rent',
    entry_type: 'expense',
    frequency: 'monthly',
    start_date: '2026-01-01',
    end_date: null,
    next_due_date: '2026-11-01',
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <FamilyProvider>
            <RecurringPage />
          </FamilyProvider>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

describe('RecurringPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 'user-1',
        email: 'u@example.com',
        display_name: 'User',
        avatar_url: null,
        timezone: 'UTC',
        family: { id: FAMILY_ID, name: 'Fam', role: 'member' },
      },
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn(),
    } as unknown as ReturnType<typeof useAuth>)
  })

  it('shows an empty state when nothing is configured', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([])
    renderPage()
    expect(await screen.findByTestId('recurring-empty')).toBeInTheDocument()
  })

  it('lists rules with frequency, amount and next date', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([makeRule()])
    renderPage()
    const row = await screen.findByTestId('recurring-row-rule-1')
    expect(row).toHaveTextContent('Rent')
    expect(row).toHaveTextContent('Monthly')
    expect(row).toHaveTextContent('$1500.00')
    expect(row).toHaveTextContent('Next')
  })

  it('pauses an active rule', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([makeRule()])
    vi.mocked(updateRecurringExpense).mockResolvedValue(makeRule({ is_active: false }))
    renderPage()
    await userEvent.click(await screen.findByTestId('recurring-toggle-rule-1'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith(FAMILY_ID, 'rule-1', { is_active: false })
    )
  })

  it('only deletes after confirmation', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([makeRule()])
    vi.mocked(deleteRecurringExpense).mockResolvedValue()
    const confirm = vi.fn().mockReturnValueOnce(false).mockReturnValueOnce(true)
    vi.stubGlobal('confirm', confirm)
    renderPage()
    const btn = await screen.findByTestId('recurring-delete-rule-1')

    await userEvent.click(btn)
    expect(deleteRecurringExpense).not.toHaveBeenCalled()

    await userEvent.click(btn)
    await waitFor(() => expect(deleteRecurringExpense).toHaveBeenCalledWith(FAMILY_ID, 'rule-1'))
    vi.unstubAllGlobals()
  })

  it('opens the create dialog', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([])
    renderPage()
    await userEvent.click(await screen.findByTestId('add-recurring-btn'))
    expect(await screen.findByTestId('recurring-amount-input')).toBeInTheDocument()
  })
})
