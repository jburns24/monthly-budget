import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import EditRecurringDialog from '../components/recurring/EditRecurringDialog'
import system from '../theme'
import type { RecurringExpense } from '../types/recurring'

vi.mock('../api/recurring', () => ({
  updateRecurringExpense: vi.fn(),
  deleteRecurringExpense: vi.fn(),
}))
vi.mock('../api/categories', () => ({
  getCategories: vi.fn(() =>
    Promise.resolve([
      { id: 'cat-1', name: 'Housing', icon: '🏠' },
      { id: 'cat-2', name: 'Fun', icon: '🎉' },
    ])
  ),
}))
vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

import { deleteRecurringExpense, updateRecurringExpense } from '../api/recurring'

// Far enough in the future that "after today" holds whenever the suite runs.
const NEXT = '2099-11-01'

function makeRule(overrides: Partial<RecurringExpense> = {}): RecurringExpense {
  return {
    id: 'rule-1',
    family_id: 'fam-1',
    category_id: 'cat-1',
    amount_cents: 150000,
    description: 'Rent',
    entry_type: 'expense',
    frequency: 'monthly',
    start_date: '2026-01-01',
    end_date: null,
    next_due_date: NEXT,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderDialog(rule: RecurringExpense, onOpenChange = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <EditRecurringDialog open onOpenChange={onOpenChange} familyId="fam-1" rule={rule} />
      </QueryClientProvider>
    </ChakraProvider>
  )
  return onOpenChange
}

async function replace(testId: string, value: string) {
  const el = await screen.findByTestId(testId)
  await userEvent.clear(el)
  if (value) await userEvent.type(el, value)
}

describe('EditRecurringDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(updateRecurringExpense).mockResolvedValue(makeRule())
  })

  it('sends only the fields that changed', async () => {
    const onOpenChange = renderDialog(makeRule())
    await replace('edit-recurring-amount', '1600.50')
    await userEvent.click(screen.getByTestId('edit-recurring-save'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1', {
        amount_cents: 160050,
      })
    )
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('sends a changed description, including clearing it', async () => {
    renderDialog(makeRule())
    await replace('edit-recurring-description', '')
    await userEvent.click(screen.getByTestId('edit-recurring-save'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1', { description: '' })
    )
  })

  it('changing frequency shows the restart hint and sends it', async () => {
    renderDialog(makeRule())
    const select = await screen.findByTestId('edit-recurring-frequency')
    expect(screen.queryByTestId('edit-recurring-frequency-hint')).not.toBeInTheDocument()
    await userEvent.selectOptions(select, 'weekly')
    expect(screen.getByTestId('edit-recurring-frequency-hint')).toBeInTheDocument()
    await userEvent.click(screen.getByTestId('edit-recurring-save'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1', {
        frequency: 'weekly',
      })
    )
  })

  it('moves the next date and clears the end date with null', async () => {
    renderDialog(makeRule({ end_date: '2099-12-31' }))
    await replace('edit-recurring-next', '2099-11-15')
    await replace('edit-recurring-end', '')
    await userEvent.click(screen.getByTestId('edit-recurring-save'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1', {
        next_due_date: '2099-11-15',
        end_date: null,
      })
    )
  })

  it('blocks a next date that is not in the future', async () => {
    renderDialog(makeRule())
    await replace('edit-recurring-next', '2020-01-01')
    expect(screen.getByTestId('edit-recurring-next-hint')).toBeInTheDocument()
    expect(screen.getByTestId('edit-recurring-save')).toBeDisabled()
  })

  it('does not block an unchanged next date even if it is due or overdue', async () => {
    renderDialog(makeRule({ next_due_date: '2020-01-01' }))
    await replace('edit-recurring-amount', '10')
    expect(screen.queryByTestId('edit-recurring-next-hint')).not.toBeInTheDocument()
    expect(screen.getByTestId('edit-recurring-save')).toBeEnabled()
  })

  it('blocks an end date before the next date', async () => {
    renderDialog(makeRule())
    await replace('edit-recurring-end', '2099-10-01')
    expect(screen.getByTestId('edit-recurring-end-hint')).toBeInTheDocument()
    expect(screen.getByTestId('edit-recurring-save')).toBeDisabled()
  })

  it('blocks zero or invalid amounts', async () => {
    renderDialog(makeRule())
    await replace('edit-recurring-amount', '0')
    expect(screen.getByTestId('edit-recurring-save')).toBeDisabled()
    await replace('edit-recurring-amount', 'abc')
    expect(screen.getByTestId('edit-recurring-save')).toBeDisabled()
  })

  it('requires a new category when the old one is archived', async () => {
    renderDialog(makeRule({ category_id: 'archived-cat' }))
    expect(await screen.findByTestId('edit-recurring-category-hint')).toBeInTheDocument()
    expect(screen.getByTestId('edit-recurring-save')).toBeDisabled()
    await userEvent.selectOptions(screen.getByTestId('edit-recurring-category'), 'cat-2')
    expect(screen.getByTestId('edit-recurring-save')).toBeEnabled()
    await userEvent.click(screen.getByTestId('edit-recurring-save'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1', {
        category_id: 'cat-2',
      })
    )
  })

  it('hides the category for income rules', async () => {
    renderDialog(makeRule({ entry_type: 'income', category_id: null }))
    await screen.findByTestId('edit-recurring-amount')
    expect(screen.queryByTestId('edit-recurring-category')).not.toBeInTheDocument()
  })

  it('tells the user an ended rule restarts when the end date is extended', async () => {
    renderDialog(makeRule({ is_active: false, end_date: '2099-10-01' }))
    expect(await screen.findByText(/has ended/i)).toBeInTheDocument()
    await replace('edit-recurring-end', '2099-12-31')
    expect(screen.getByText(/start the entry running again/i)).toBeInTheDocument()
    await userEvent.click(screen.getByTestId('edit-recurring-save'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1', {
        end_date: '2099-12-31',
      })
    )
  })

  it('pauses an active rule from the dialog', async () => {
    const onOpenChange = renderDialog(makeRule())
    await userEvent.click(await screen.findByTestId('edit-recurring-toggle'))
    await waitFor(() =>
      expect(updateRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1', { is_active: false })
    )
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })

  it('offers Resume for a paused rule', async () => {
    renderDialog(makeRule({ is_active: false }))
    expect(await screen.findByTestId('edit-recurring-toggle')).toHaveTextContent('Resume')
  })

  it('has no Pause/Resume for an ended rule', async () => {
    renderDialog(makeRule({ is_active: false, end_date: '2099-10-01' }))
    await screen.findByTestId('edit-recurring-amount')
    expect(screen.queryByTestId('edit-recurring-toggle')).not.toBeInTheDocument()
  })

  it('only deletes after the inline confirmation', async () => {
    vi.mocked(deleteRecurringExpense).mockResolvedValue()
    const onOpenChange = renderDialog(makeRule())
    await userEvent.click(await screen.findByTestId('edit-recurring-delete'))
    expect(deleteRecurringExpense).not.toHaveBeenCalled()
    await userEvent.click(screen.getByText('Keep'))
    expect(screen.getByTestId('edit-recurring-save')).toBeInTheDocument()
    await userEvent.click(screen.getByTestId('edit-recurring-delete'))
    await userEvent.click(screen.getByTestId('edit-recurring-delete-confirm'))
    await waitFor(() => expect(deleteRecurringExpense).toHaveBeenCalledWith('fam-1', 'rule-1'))
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
  })
})
