import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import BulkGoalsEditor from '../components/goals/BulkGoalsEditor'
import type { MonthlyGoal } from '../types/goals'
import type { Category } from '../types/categories'
import system from '../theme'

vi.mock('../api/goals', () => ({
  updateGoalsBulk: vi.fn(() => new Promise(() => {})),
}))

vi.mock('../components/ui/toaster', () => ({
  toaster: {
    create: vi.fn(),
  },
  Toaster: vi.fn(() => null),
}))

import { updateGoalsBulk } from '../api/goals'

const FAMILY_ID = 'fam-123'
const YEAR_MONTH = '2026-04'

const categories: Category[] = [
  {
    id: 'cat-1',
    family_id: FAMILY_ID,
    name: 'Groceries',
    icon: '🛒',
    sort_order: 0,
    is_active: true,
    created_at: '2026-04-01T00:00:00Z',
  },
  {
    id: 'cat-2',
    family_id: FAMILY_ID,
    name: 'Transport',
    icon: '🚌',
    sort_order: 1,
    is_active: true,
    created_at: '2026-04-01T00:00:00Z',
  },
]

function makeGoal(overrides: Partial<MonthlyGoal> = {}): MonthlyGoal {
  return {
    id: 'goal-1',
    family_id: FAMILY_ID,
    category_id: 'cat-1',
    year_month: YEAR_MONTH,
    amount_cents: 60000,
    version: 1,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-01T00:00:00Z',
    ...overrides,
  }
}

function renderBulkEditor(currentGoals: MonthlyGoal[] = []) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <BulkGoalsEditor
          isOpen={true}
          onClose={vi.fn()}
          familyId={FAMILY_ID}
          yearMonth={YEAR_MONTH}
          categories={categories}
          currentGoals={currentGoals}
        />
      </QueryClientProvider>
    </ChakraProvider>
  )
}

describe('BulkGoalsEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('explains that blank leaves a goal unchanged', async () => {
    renderBulkEditor([makeGoal()])

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(
      screen.getByText(/leave a category blank to leave its goal unchanged/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/leave blank to remove/i)).not.toBeInTheDocument()
  })

  it('omits blank categories from the bulk payload so existing goals are not sent for deletion', async () => {
    const user = userEvent.setup()
    vi.mocked(updateGoalsBulk).mockResolvedValue({
      year_month: YEAR_MONTH,
      created: 0,
      updated: 1,
      deleted: 0,
      goals: [makeGoal({ amount_cents: 70000 })],
    })

    renderBulkEditor([
      makeGoal({ id: 'goal-1', category_id: 'cat-1', amount_cents: 60000 }),
      makeGoal({ id: 'goal-2', category_id: 'cat-2', amount_cents: 15000 }),
    ])

    await waitFor(() => {
      expect(screen.getByTestId('goal-input-cat-1')).toBeInTheDocument()
    })

    const groceriesInput = screen.getByTestId('goal-input-cat-1')
    await user.clear(groceriesInput)
    await user.type(groceriesInput, '700.00')
    await user.clear(screen.getByTestId('goal-input-cat-2'))

    await user.click(screen.getByTestId('bulk-goals-save-btn'))

    await waitFor(() => {
      expect(updateGoalsBulk).toHaveBeenCalledWith(
        FAMILY_ID,
        expect.objectContaining({
          year_month: YEAR_MONTH,
          goals: [{ category_id: 'cat-1', amount_cents: 70000 }],
        })
      )
    })
  })
})
