import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import DashboardPage from '../pages/DashboardPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'

// Mock useAuth to control auth + family state
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

// Mock expenses API to prevent real HTTP calls
vi.mock('../api/expenses', () => ({
  getBudgetSummary: vi.fn(() => new Promise(() => {})),
  getExpenses: vi.fn(() => new Promise(() => {})),
  createExpense: vi.fn(() => new Promise(() => {})),
  updateExpense: vi.fn(() => new Promise(() => {})),
  deleteExpense: vi.fn(() => new Promise(() => {})),
}))

// Mock goals API to prevent real HTTP calls
vi.mock('../api/goals', () => ({
  getGoals: vi.fn(() => new Promise(() => {})),
  updateGoal: vi.fn(() => new Promise(() => {})),
  updateGoalsBulk: vi.fn(() => new Promise(() => {})),
  deleteGoal: vi.fn(() => new Promise(() => {})),
  rolloverGoals: vi.fn(() => new Promise(() => {})),
}))

// Mock categories API to prevent real HTTP calls
vi.mock('../api/categories', () => ({
  getCategories: vi.fn(() => new Promise(() => {})),
  createCategory: vi.fn(() => new Promise(() => {})),
  updateCategory: vi.fn(() => new Promise(() => {})),
  deleteCategory: vi.fn(() => new Promise(() => {})),
  seedCategories: vi.fn(() => new Promise(() => {})),
}))

// Mock PendingInvites to avoid sub-tree complexity
vi.mock('../components/family/PendingInvites', () => ({
  default: vi.fn(() => <div data-testid="pending-invites" />),
}))

// Mock CreateExpenseDialog (used inside FAB) to avoid localStorage/complex deps
vi.mock('../components/expenses/CreateExpenseDialog', () => ({
  default: vi.fn(({ open }: { open: boolean }) =>
    open ? <div role="dialog" data-testid="create-expense-dialog" /> : null
  ),
}))

// Mock SetGoalDialog to avoid complex form dependencies in these tests
vi.mock('../components/goals/SetGoalDialog', () => ({
  default: vi.fn(({ open }: { open: boolean }) =>
    open ? <div role="dialog" data-testid="set-goal-dialog" /> : null
  ),
}))

// Mock BulkGoalsEditor to avoid complex form dependencies in these tests
vi.mock('../components/goals/BulkGoalsEditor', () => ({
  default: vi.fn(({ isOpen }: { isOpen: boolean }) =>
    isOpen ? <div role="dialog" data-testid="bulk-goals-editor" /> : null
  ),
}))

// Mock RolloverPrompt to simplify rollover banner testing
vi.mock('../components/goals/RolloverPrompt', () => ({
  default: vi.fn(({ hasPreviousGoals }: { hasPreviousGoals: boolean }) =>
    hasPreviousGoals ? <div data-testid="rollover-prompt" /> : null
  ),
}))

import { useAuth } from '../hooks/useAuth'
import { getBudgetSummary } from '../api/expenses'
import { getGoals } from '../api/goals'

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

function makeAdminWithFamily() {
  return {
    id: 'user-admin',
    email: 'admin@example.com',
    display_name: 'Admin User',
    avatar_url: null,
    timezone: 'UTC',
    family: { id: FAMILY_ID, name: 'Test Family', role: 'admin' as const },
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

function renderDashboardPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/']}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <FamilyProvider>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/expenses" element={<div data-testid="expenses-page" />} />
              <Route path="/family" element={<div data-testid="family-page" />} />
            </Routes>
          </FamilyProvider>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

const sampleSummaryWithSpending = {
  year_month: '2026-04',
  total_spent_cents: 15000,
  categories: [
    {
      category_id: 'cat-1',
      category_name: 'Groceries',
      icon: '🛒',
      spent_cents: 5000,
      goal_cents: 10000,
      percentage: 50,
      status: 'green',
    },
    {
      category_id: 'cat-2',
      category_name: 'Transport',
      icon: '🚗',
      spent_cents: 8200,
      goal_cents: 9000,
      percentage: 91.1,
      status: 'yellow',
    },
    {
      category_id: 'cat-3',
      category_name: 'Dining',
      icon: '🍽️',
      spent_cents: 1800,
      goal_cents: 1500,
      percentage: 120,
      status: 'red',
    },
  ],
}

const sampleSummaryEmpty = {
  year_month: '2026-04',
  total_spent_cents: 0,
  categories: [
    {
      category_id: 'cat-1',
      category_name: 'Groceries',
      icon: '🛒',
      spent_cents: 0,
      goal_cents: 10000,
      percentage: 0,
      status: 'green',
    },
  ],
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ------------------------------------------------------------------ loading
  it('renders loading spinner while budget summary is fetching', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    // getBudgetSummary stays pending (loading state)

    renderDashboardPage()

    expect(screen.getByLabelText('Loading budget summary')).toBeInTheDocument()
  })

  // ------------------------------------------------------------------ budget summary
  it('renders total spent and category cards when data loads', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByText(/\$150/)).toBeInTheDocument()
    })

    expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    expect(screen.getByLabelText('Transport category')).toBeInTheDocument()
    expect(screen.getByLabelText('Dining category')).toBeInTheDocument()
  })

  // ------------------------------------------------------------------ progress colors
  it('green status renders accent color for category under 80%', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    // The Groceries card has status=green, percentage=50 → shows 50%
    const groceriesCard = screen.getByLabelText('Groceries category')
    expect(groceriesCard).toBeInTheDocument()
    // The percentage text is rendered inside the card
    expect(groceriesCard.textContent).toContain('50%')
  })

  it('yellow status shown for category between 80-99%', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Transport category')).toBeInTheDocument()
    })

    const transportCard = screen.getByLabelText('Transport category')
    // Transport: percentage=91.1, rounded to 91%
    expect(transportCard.textContent).toContain('91%')
  })

  it('red status shown for category at or above 100%', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Dining category')).toBeInTheDocument()
    })

    const diningCard = screen.getByLabelText('Dining category')
    // Dining: percentage=120 → shows 100% (capped bar) but label shows 120%
    expect(diningCard.textContent).toContain('120%')
  })

  // ------------------------------------------------------------------ month selector
  it('renders month selector with prev and next buttons', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    expect(screen.getByRole('button', { name: 'Previous month' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next month' })).toBeInTheDocument()
  })

  it('clicking next month changes the month heading', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    const heading = screen.getByRole('heading')
    const initialMonth = heading.textContent ?? ''

    await user.click(screen.getByRole('button', { name: 'Next month' }))

    const updatedHeading = screen.getByRole('heading')
    expect(updatedHeading.textContent).not.toBe(initialMonth)
  })

  it('clicking prev month changes the month heading', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    const heading = screen.getByRole('heading')
    const initialMonth = heading.textContent ?? ''

    await user.click(screen.getByRole('button', { name: 'Previous month' }))

    const updatedHeading = screen.getByRole('heading')
    expect(updatedHeading.textContent).not.toBe(initialMonth)
  })

  // ------------------------------------------------------------------ FAB / expense dialog
  it('renders FAB button when user has a family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    expect(screen.getByTestId('fab-add-expense')).toBeInTheDocument()
  })

  it('does not render FAB when user has no family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithoutFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    expect(screen.queryByTestId('fab-add-expense')).not.toBeInTheDocument()
  })

  it('clicking FAB opens create expense dialog', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    await user.click(screen.getByTestId('fab-add-expense'))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  // ------------------------------------------------------------------ empty state
  it('shows empty state CTA when family exists but no expenses this month', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryEmpty)

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByText(/no expenses this month/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/add your first expense/i)).toBeInTheDocument()
  })

  // ------------------------------------------------------------------ no family state
  it('shows pending invites and CTA when user has no family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithoutFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    expect(screen.getByTestId('pending-invites')).toBeInTheDocument()
    // Both the descriptive text and the CTA button contain this phrase
    const elements = screen.getAllByText(/create or join a family/i)
    expect(elements.length).toBeGreaterThanOrEqual(1)
  })

  it('navigates to /family when "Create or join a family" button clicked', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithoutFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderDashboardPage()

    const ctaButton = screen.getByRole('button', { name: /create or join a family/i })
    await user.click(ctaButton)

    await waitFor(() => {
      expect(screen.getByTestId('family-page')).toBeInTheDocument()
    })
  })

  // ------------------------------------------------------------------ error state
  it('shows error message when budget summary query fails', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockRejectedValue(new Error('Network error'))

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByText(/failed to load budget summary/i)).toBeInTheDocument()
    })
  })

  // ------------------------------------------------------------------ category click navigation
  it('clicking a category card navigates to expenses page filtered by category', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    await user.click(screen.getByLabelText('Groceries category'))

    await waitFor(() => {
      expect(screen.getByTestId('expenses-page')).toBeInTheDocument()
    })
  })

  // ------------------------------------------------------------------ goal buttons (admin)
  it('admin sees "Set Goal" buttons on category cards when no goals exist', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [],
      has_previous_goals: false,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    // Admin should see "Set Goal +" buttons (one per category)
    const setGoalButtons = screen.getAllByText(/set goal/i)
    expect(setGoalButtons.length).toBeGreaterThan(0)
  })

  it('admin sees "Edit Goal" button on category card when goal exists', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [
        {
          id: 'goal-1',
          family_id: FAMILY_ID,
          category_id: 'cat-1',
          year_month: '2026-04',
          amount_cents: 10000,
          version: 1,
          created_at: '2026-04-01T00:00:00Z',
          updated_at: '2026-04-01T00:00:00Z',
        },
      ],
      has_previous_goals: false,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    // The cat-1 (Groceries) card should have "Edit Goal" button
    expect(screen.getByTestId('edit-goal-btn-cat-1')).toBeInTheDocument()
    // Other categories should still have "Set Goal" buttons
    expect(screen.getByTestId('set-goal-btn-cat-2')).toBeInTheDocument()
  })

  it('member does not see goal buttons on category cards', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [],
      has_previous_goals: false,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    // Members should NOT see goal buttons
    expect(screen.queryByText(/set goal/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/edit goal/i)).not.toBeInTheDocument()
  })

  // ------------------------------------------------------------------ manage all goals button
  it('admin sees "Manage All Goals" button when categories are loaded', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [],
      has_previous_goals: false,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByTestId('manage-goals-btn')).toBeInTheDocument()
    })
  })

  it('member does not see "Manage All Goals" button', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [],
      has_previous_goals: false,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('manage-goals-btn')).not.toBeInTheDocument()
  })

  // ------------------------------------------------------------------ rollover prompt
  it('admin sees rollover prompt when no goals for current month but previous month has goals', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [],
      has_previous_goals: true,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByTestId('rollover-prompt')).toBeInTheDocument()
    })
  })

  it('member does not see rollover prompt even when previous goals exist', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeUserWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [],
      has_previous_goals: true,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('rollover-prompt')).not.toBeInTheDocument()
  })

  it('rollover prompt is not shown when current month already has goals', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminWithFamily(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getBudgetSummary).mockResolvedValue(sampleSummaryWithSpending)
    vi.mocked(getGoals).mockResolvedValue({
      year_month: '2026-04',
      goals: [
        {
          id: 'goal-1',
          family_id: FAMILY_ID,
          category_id: 'cat-1',
          year_month: '2026-04',
          amount_cents: 10000,
          version: 1,
          created_at: '2026-04-01T00:00:00Z',
          updated_at: '2026-04-01T00:00:00Z',
        },
      ],
      has_previous_goals: true,
    })

    renderDashboardPage()

    await waitFor(() => {
      expect(screen.getByLabelText('Groceries category')).toBeInTheDocument()
    })

    expect(screen.queryByTestId('rollover-prompt')).not.toBeInTheDocument()
  })
})
