import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import ExpensesPage from '../pages/ExpensesPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'

// Mock useAuth to control auth + family state
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

// Mock expenses API to prevent real HTTP calls
vi.mock('../api/expenses', () => ({
  getExpenses: vi.fn(() => new Promise(() => {})),
  createExpense: vi.fn(() => new Promise(() => {})),
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

// Mock dialog components to avoid complex sub-tree dependencies (e.g. localStorage in CreateExpenseDialog)
vi.mock('../components/expenses/CreateExpenseDialog', () => ({
  default: vi.fn(({ open }: { open: boolean }) =>
    open ? <div role="dialog" data-testid="create-expense-dialog" /> : null
  ),
}))

vi.mock('../components/expenses/EditExpenseDialog', () => ({
  default: vi.fn(({ open }: { open: boolean }) =>
    open ? <div role="dialog" data-testid="edit-expense-dialog" /> : null
  ),
}))

vi.mock('../components/expenses/DeleteExpenseDialog', () => ({
  default: vi.fn(({ open }: { open: boolean }) =>
    open ? <div role="dialog" data-testid="delete-expense-dialog" /> : null
  ),
}))

import { useAuth } from '../hooks/useAuth'
import { getExpenses } from '../api/expenses'
import { getCategories } from '../api/categories'

const FAMILY_ID = 'fam-123'

function makeUserWithFamily() {
  return {
    id: 'user-1',
    email: 'user@example.com',
    display_name: 'Test User',
    avatar_url: null,
    timezone: 'UTC',
    family: { id: FAMILY_ID, name: 'Test Family', role: 'member' as const },
  }
}

function makeUserWithoutFamily() {
  return {
    id: 'user-2',
    email: 'nofamily@example.com',
    display_name: 'No Family User',
    avatar_url: null,
    timezone: 'UTC',
    family: null,
  }
}

function renderExpensesPage(initialPath = '/expenses') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <FamilyProvider>
            <Routes>
              <Route path="/expenses" element={<ExpensesPage />} />
            </Routes>
          </FamilyProvider>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

const sampleExpenses = [
  {
    id: 'exp-1',
    family_id: FAMILY_ID,
    category: { id: 'cat-1', name: 'Groceries', icon: '🛒' },
    created_by_user: { id: 'user-1', display_name: 'Alice' },
    amount_cents: 4523,
    description: 'Weekly groceries',
    expense_date: '2026-04-01',
    created_at: '2026-04-01T10:00:00Z',
    updated_at: '2026-04-01T10:00:00Z',
  },
  {
    id: 'exp-2',
    family_id: FAMILY_ID,
    category: { id: 'cat-2', name: 'Transport', icon: '🚗' },
    created_by_user: { id: 'user-2', display_name: 'Bob' },
    amount_cents: 1500,
    description: 'Bus pass',
    expense_date: '2026-04-03',
    created_at: '2026-04-03T08:00:00Z',
    updated_at: '2026-04-03T08:00:00Z',
  },
]

const sampleExpenseListResponse = {
  expenses: sampleExpenses,
  total_count: 2,
  page: 1,
  per_page: 20,
}

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

describe('ExpensesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading spinner while expenses are fetching', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    // getExpenses returns a never-resolving promise (loading state)
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    expect(screen.getByLabelText('Loading expenses')).toBeInTheDocument()
  })

  it('renders expense list with correct data when loaded', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    await waitFor(() => {
      expect(screen.getByTestId('expense-card-exp-1')).toBeInTheDocument()
      expect(screen.getByTestId('expense-card-exp-2')).toBeInTheDocument()
    })
  })

  it('shows month display in header', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    expect(screen.getByTestId('month-display')).toBeInTheDocument()
  })

  it('prev/next month buttons are present and clickable', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    const prevBtn = screen.getByTestId('prev-month-btn')
    const nextBtn = screen.getByTestId('next-month-btn')
    expect(prevBtn).toBeInTheDocument()
    expect(nextBtn).toBeInTheDocument()

    // Record initial month display
    const monthDisplay = screen.getByTestId('month-display')
    const initialMonth = monthDisplay.textContent

    // Click next month changes display
    await user.click(nextBtn)
    const afterNextMonth = screen.getByTestId('month-display').textContent
    expect(afterNextMonth).not.toBe(initialMonth)

    // Click prev month goes back to initial
    await user.click(prevBtn)
    await user.click(prevBtn)
    const afterPrevMonth = screen.getByTestId('month-display').textContent
    expect(afterPrevMonth).not.toBe(afterNextMonth)
  })

  it('shows category filter when categories are available', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderExpensesPage()

    await waitFor(() => {
      expect(screen.getByTestId('category-filter-select')).toBeInTheDocument()
    })

    // Should show all categories as options
    const select = screen.getByTestId('category-filter-select')
    expect(select).toBeInTheDocument()
    const options = Array.from(select.querySelectorAll('option'))
    const optionTexts = options.map((o) => o.textContent ?? '')
    expect(optionTexts.some((t) => t.includes('Groceries'))).toBe(true)
    expect(optionTexts.some((t) => t.includes('Transport'))).toBe(true)
    expect(optionTexts.some((t) => t.includes('All Categories'))).toBe(true)
  })

  it('does not show category filter when no categories', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    expect(screen.queryByTestId('category-filter-select')).not.toBeInTheDocument()
  })

  it('category filter change triggers new query', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderExpensesPage()

    await waitFor(() => {
      expect(screen.getByTestId('category-filter-select')).toBeInTheDocument()
    })

    const select = screen.getByTestId('category-filter-select')
    await user.selectOptions(select, 'cat-1')

    await waitFor(() => {
      // getExpenses should have been called with the selected category id
      const calls = vi.mocked(getExpenses).mock.calls
      const hasFilteredCall = calls.some((call) => call[2] === 'cat-1')
      expect(hasFilteredCall).toBe(true)
    })
  })

  it('shows pagination controls when total_count > per_page', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    // Simulate 25 expenses, 20 per page → 2 pages
    vi.mocked(getExpenses).mockResolvedValue({
      expenses: sampleExpenses,
      total_count: 25,
      page: 1,
      per_page: 20,
    })
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    await waitFor(() => {
      expect(screen.getByTestId('pagination-controls')).toBeInTheDocument()
    })

    expect(screen.getByTestId('prev-page-btn')).toBeInTheDocument()
    expect(screen.getByTestId('next-page-btn')).toBeInTheDocument()
    expect(screen.getByTestId('page-indicator')).toHaveTextContent('Page 1 of 2')
  })

  it('does not show pagination controls when total_count <= per_page', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    await waitFor(() => {
      expect(screen.getByTestId('expense-card-exp-1')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('pagination-controls')).not.toBeInTheDocument()
  })

  it('shows empty state message when no expenses for the month', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue({
      expenses: [],
      total_count: 0,
      page: 1,
      per_page: 20,
    })
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    await waitFor(() => {
      expect(screen.getByTestId('expense-list-empty')).toBeInTheDocument()
    })
  })

  it('shows Add Expense button when user has a family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    expect(screen.getByTestId('add-expense-btn')).toBeInTheDocument()
  })

  it('does not show Add Expense button when user has no family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithoutFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderExpensesPage()

    expect(screen.queryByTestId('add-expense-btn')).not.toBeInTheDocument()
  })

  it('shows "no family" message when user has no family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithoutFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderExpensesPage()

    expect(screen.getByText(/create or join a family/i)).toBeInTheDocument()
  })

  it('opens create expense dialog when Add Expense button is clicked', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    await user.click(screen.getByTestId('add-expense-btn'))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  it('shows error message when expenses query fails', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockRejectedValue(new Error('Network error'))
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    await waitFor(() => {
      expect(screen.getByText(/failed to load expenses/i)).toBeInTheDocument()
    })
  })

  it('initializes month from URL search params', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage('/expenses?month=2025-06')

    expect(screen.getByTestId('month-display')).toHaveTextContent('June 2025')
  })

  it('shows month label with expense count in summary line', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getExpenses).mockResolvedValue(sampleExpenseListResponse)
    vi.mocked(getCategories).mockResolvedValue([])

    renderExpensesPage()

    await waitFor(() => {
      const label = screen.getByTestId('expenses-month-label')
      expect(label).toBeInTheDocument()
      expect(label.textContent).toMatch(/2 expense/)
    })
  })
})
