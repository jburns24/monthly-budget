import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import SetGoalDialog from '../components/goals/SetGoalDialog'
import type { MonthlyGoal } from '../types/goals'
import system from '../theme'

// Mock goals API to prevent real HTTP calls
vi.mock('../api/goals', () => ({
  getGoals: vi.fn(() => new Promise(() => {})),
  updateGoal: vi.fn(() => new Promise(() => {})),
  updateGoalsBulk: vi.fn(() => new Promise(() => {})),
  deleteGoal: vi.fn(() => new Promise(() => {})),
  rolloverGoals: vi.fn(() => new Promise(() => {})),
}))

// Mock the toaster to avoid rendering issues in tests
vi.mock('../components/ui/toaster', () => ({
  toaster: {
    create: vi.fn(),
  },
  Toaster: vi.fn(() => null),
}))

import { updateGoal, updateGoalsBulk } from '../api/goals'
import { toaster } from '../components/ui/toaster'

const FAMILY_ID = 'fam-123'
const YEAR_MONTH = '2026-04'
const CATEGORY_ID = 'cat-1'
const CATEGORY_NAME = 'Dining Out'

function makeGoal(overrides: Partial<MonthlyGoal> = {}): MonthlyGoal {
  return {
    id: 'goal-1',
    family_id: FAMILY_ID,
    category_id: CATEGORY_ID,
    year_month: YEAR_MONTH,
    amount_cents: 60000,
    version: 1,
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-01T00:00:00Z',
    ...overrides,
  }
}

function renderSetGoalDialog(
  open = true,
  onOpenChange = vi.fn(),
  existingGoal?: MonthlyGoal | null
) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <SetGoalDialog
          open={open}
          onOpenChange={onOpenChange}
          familyId={FAMILY_ID}
          yearMonth={YEAR_MONTH}
          categoryId={CATEGORY_ID}
          categoryName={CATEGORY_NAME}
          existingGoal={existingGoal}
        />
      </QueryClientProvider>
    </ChakraProvider>
  )
}

describe('SetGoalDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ------------------------------------------------------------------ dialog title
  it('renders "Set Goal" title with category name when no existing goal', async () => {
    renderSetGoalDialog(true, vi.fn(), null)

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByText(`Set Goal — ${CATEGORY_NAME}`)).toBeInTheDocument()
  })

  it('renders "Edit Goal" title with category name when existing goal is provided', async () => {
    renderSetGoalDialog(true, vi.fn(), makeGoal())

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByText(`Edit Goal — ${CATEGORY_NAME}`)).toBeInTheDocument()
  })

  // ------------------------------------------------------------------ form fields
  it('renders amount input and save/cancel buttons when open', async () => {
    renderSetGoalDialog()

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    expect(screen.getByTestId('goal-amount-input')).toBeInTheDocument()
    expect(screen.getByTestId('goal-save-btn')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()
  })

  it('save button is disabled when amount input is empty', async () => {
    renderSetGoalDialog(true, vi.fn(), null)

    await waitFor(() => {
      expect(screen.getByTestId('goal-save-btn')).toBeInTheDocument()
    })

    expect(screen.getByTestId('goal-save-btn')).toBeDisabled()
  })

  // ------------------------------------------------------------------ new goal mutation
  it('calls updateGoalsBulk with correct cents and shows success toast on new goal save', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()

    vi.mocked(updateGoalsBulk).mockResolvedValue({
      year_month: YEAR_MONTH,
      created: 1,
      updated: 0,
      deleted: 0,
      goals: [makeGoal({ amount_cents: 20000 })],
    })

    renderSetGoalDialog(true, onOpenChange, null)

    await waitFor(() => {
      expect(screen.getByTestId('goal-amount-input')).toBeInTheDocument()
    })

    await user.type(screen.getByTestId('goal-amount-input'), '200.00')

    await waitFor(() => {
      expect(screen.getByTestId('goal-save-btn')).not.toBeDisabled()
    })

    await user.click(screen.getByTestId('goal-save-btn'))

    await waitFor(() => {
      expect(updateGoalsBulk).toHaveBeenCalledWith(
        FAMILY_ID,
        expect.objectContaining({
          year_month: YEAR_MONTH,
          goals: expect.arrayContaining([
            expect.objectContaining({
              category_id: CATEGORY_ID,
              amount_cents: 20000,
            }),
          ]),
        })
      )
    })

    await waitFor(() => {
      expect(toaster.create).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' }))
    })

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  // ------------------------------------------------------------------ API error handling
  it('shows error toast and keeps dialog open when API call fails', async () => {
    const user = userEvent.setup()
    const onOpenChange = vi.fn()

    vi.mocked(updateGoalsBulk).mockRejectedValue(new Error('Network error'))

    renderSetGoalDialog(true, onOpenChange, null)

    await waitFor(() => {
      expect(screen.getByTestId('goal-amount-input')).toBeInTheDocument()
    })

    await user.type(screen.getByTestId('goal-amount-input'), '150.00')

    await waitFor(() => {
      expect(screen.getByTestId('goal-save-btn')).not.toBeDisabled()
    })

    await user.click(screen.getByTestId('goal-save-btn'))

    await waitFor(() => {
      expect(toaster.create).toHaveBeenCalledWith(expect.objectContaining({ type: 'error' }))
    })

    // Dialog should remain open (onOpenChange not called with false)
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
  })

  // ------------------------------------------------------------------ existing goal mutation
  it('calls updateGoal with expected_version when editing an existing goal', async () => {
    const user = userEvent.setup()
    const existingGoal = makeGoal({ amount_cents: 60000, version: 2 })
    const onOpenChange = vi.fn()

    vi.mocked(updateGoal).mockResolvedValue({ ...existingGoal, amount_cents: 70000 })

    renderSetGoalDialog(true, onOpenChange, existingGoal)

    await waitFor(() => {
      expect(screen.getByTestId('goal-amount-input')).toBeInTheDocument()
    })

    // Clear existing value and type new amount
    const amountInput = screen.getByTestId('goal-amount-input')
    await user.clear(amountInput)
    await user.type(amountInput, '700.00')

    await waitFor(() => {
      expect(screen.getByTestId('goal-save-btn')).not.toBeDisabled()
    })

    await user.click(screen.getByTestId('goal-save-btn'))

    await waitFor(() => {
      expect(updateGoal).toHaveBeenCalledWith(
        FAMILY_ID,
        existingGoal.id,
        expect.objectContaining({
          amount_cents: 70000,
          expected_version: 2,
        })
      )
    })

    await waitFor(() => {
      expect(toaster.create).toHaveBeenCalledWith(expect.objectContaining({ type: 'success' }))
    })

    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
