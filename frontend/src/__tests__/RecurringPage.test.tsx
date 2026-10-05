import { render, screen } from '@testing-library/react'
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
import { getRecurringExpenses } from '../api/recurring'

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
    expect(row).toHaveTextContent('−$1,500')
    expect(row).toHaveTextContent('Next')
  })

  it('opens the create dialog', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([])
    renderPage()
    await userEvent.click(await screen.findByTestId('add-recurring-btn'))
    expect(await screen.findByTestId('recurring-amount-input')).toBeInTheDocument()
  })

  it('shows Ended in the meta line for a rule past its end date', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([
      makeRule({ is_active: false, end_date: '2026-10-01', next_due_date: '2026-11-01' }),
    ])
    renderPage()
    expect(await screen.findByTestId('recurring-meta-rule-1')).toHaveTextContent(/^Ended/)
  })

  it('shows Paused in the meta line for a user-paused rule, without a Next date', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([makeRule({ is_active: false })])
    renderPage()
    const meta = await screen.findByTestId('recurring-meta-rule-1')
    expect(meta).toHaveTextContent(/^Paused/)
    expect(meta).not.toHaveTextContent('Next')
  })

  it('lists active rules before paused and ended ones', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([
      makeRule({
        id: 'ended',
        is_active: false,
        end_date: '2026-10-01',
        next_due_date: '2026-11-01',
      }),
      makeRule({ id: 'paused', is_active: false }),
      makeRule({ id: 'active' }),
    ])
    renderPage()
    await screen.findByTestId('recurring-list')
    const ids = screen.getAllByTestId(/^recurring-row-/).map((el) => el.getAttribute('data-testid'))
    expect(ids).toEqual(['recurring-row-active', 'recurring-row-paused', 'recurring-row-ended'])
  })

  it('shows income with a plus sign and the other rows with a minus', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([
      makeRule({ id: 'inc', entry_type: 'income', category_id: null, description: 'Pay' }),
    ])
    renderPage()
    expect(await screen.findByTestId('recurring-row-inc')).toHaveTextContent('+$1,500')
  })

  it('opens the edit dialog prefilled from the rule', async () => {
    vi.mocked(getRecurringExpenses).mockResolvedValue([makeRule()])
    renderPage()
    await userEvent.click(await screen.findByTestId('recurring-edit-rule-1'))
    expect(await screen.findByTestId('edit-recurring-amount')).toHaveValue('1500')
    expect(screen.getByTestId('edit-recurring-description')).toHaveValue('Rent')
    expect(screen.getByTestId('edit-recurring-frequency')).toHaveValue('monthly')
    expect(screen.getByTestId('edit-recurring-next')).toHaveValue('2026-11-01')
  })
})
