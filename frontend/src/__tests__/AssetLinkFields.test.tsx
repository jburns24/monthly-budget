import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import CreateExpenseDialog from '../components/expenses/CreateExpenseDialog'
import EditExpenseDialog from '../components/expenses/EditExpenseDialog'
import CreateRecurringDialog from '../components/recurring/CreateRecurringDialog'
import EditRecurringDialog from '../components/recurring/EditRecurringDialog'
import system from '../theme'
import type { AssetListItem } from '../types/asset'
import type { Expense } from '../types/expenses'
import type { RecurringExpense } from '../types/recurring'

vi.mock('../api/expenses', () => ({
  createExpense: vi.fn(),
  updateExpense: vi.fn(),
  deleteExpense: vi.fn(),
}))
vi.mock('../api/recurring', () => ({
  createRecurringExpense: vi.fn(),
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
vi.mock('../api/assets', () => ({ getAssets: vi.fn() }))
vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

import { createExpense, updateExpense } from '../api/expenses'
import { createRecurringExpense, updateRecurringExpense } from '../api/recurring'
import { getAssets } from '../api/assets'

// happy-dom has no usable localStorage; CreateExpenseDialog remembers the last category in it.
Object.defineProperty(globalThis, 'localStorage', {
  value: { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} },
  writable: true,
})

const FAMILY_ID = 'fam-1'

function makeAsset(overrides: Partial<AssetListItem> = {}): AssetListItem {
  return {
    id: 'asset-house',
    family_id: FAMILY_ID,
    created_by_user_id: 'u1',
    name: 'Maple Street',
    asset_type: 'house',
    purchase_date: '2021-06-01',
    purchase_price_cents: 40000000,
    down_payment_cents: 0,
    closing_costs_cents: 0,
    address_line1: null,
    city: null,
    state: 'NC',
    zip_code: '27601',
    annual_depreciation_rate: null,
    sold_date: null,
    sale_price_cents: null,
    selling_costs_cents: null,
    is_sold: false,
    created_at: '',
    updated_at: '',
    has_loan: true,
    summary: {
      market_value_cents: 45000000,
      loan_balance_cents: 30000000,
      equity_cents: 15000000,
      cash_in_cents: 1,
      valuation_source: 'fhfa_zip3',
    },
    ...overrides,
  }
}

const house = makeAsset()
const car = makeAsset({
  id: 'asset-car',
  name: 'Minivan',
  asset_type: 'vehicle',
  has_loan: false,
  summary: {
    market_value_cents: 2000000,
    loan_balance_cents: 0,
    equity_cents: 2000000,
    cash_in_cents: 3000000,
    valuation_source: 'depreciation',
  },
})
const oldBoat = makeAsset({
  id: 'asset-boat',
  name: 'Old boat',
  is_sold: true,
  sold_date: '2025-01-01',
})

function wrap(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </ChakraProvider>
  )
}

function makeExpense(overrides: Partial<Expense> = {}): Expense {
  return {
    id: 'exp-1',
    family_id: FAMILY_ID,
    category: { id: 'cat-1', name: 'Housing', icon: '🏠' },
    created_by_user: { id: 'u1', display_name: 'Alice' },
    amount_cents: 4523,
    description: 'Gutters',
    expense_date: '2026-04-01',
    created_at: '',
    updated_at: '2026-04-01T10:00:00Z',
    receipt_id: null,
    receipt_status: null,
    entry_type: 'expense',
    is_starting_balance: false,
    ...overrides,
  }
}

function makeRule(overrides: Partial<RecurringExpense> = {}): RecurringExpense {
  return {
    id: 'rule-1',
    family_id: FAMILY_ID,
    category_id: 'cat-1',
    amount_cents: 150000,
    description: 'Mortgage',
    entry_type: 'expense',
    frequency: 'monthly',
    start_date: '2026-01-01',
    end_date: null,
    next_due_date: '2099-11-01',
    is_active: true,
    created_at: '',
    updated_at: '',
    ...overrides,
  }
}

async function selectAsset(assetId: string) {
  const select = await screen.findByTestId('asset-link-select')
  await waitFor(() => expect(select.querySelectorAll('option').length).toBeGreaterThan(1))
  await userEvent.selectOptions(select, assetId)
}

describe('asset link on the expense and recurring dialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAssets).mockResolvedValue([house, car, oldBoat])
    vi.mocked(createExpense).mockResolvedValue(makeExpense())
    vi.mocked(updateExpense).mockResolvedValue(makeExpense())
    vi.mocked(createRecurringExpense).mockResolvedValue(makeRule())
    vi.mocked(updateRecurringExpense).mockResolvedValue(makeRule())
  })

  describe('CreateExpenseDialog', () => {
    async function fillAmount() {
      await userEvent.type(await screen.findByTestId('expense-amount-input'), '85')
      await waitFor(() => expect(screen.getByTestId('expense-submit-btn')).toBeEnabled())
    }

    it('offers active assets but not sold ones', async () => {
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      const select = await screen.findByTestId('asset-link-select')
      await waitFor(() => expect(select.querySelectorAll('option').length).toBe(3))
      const names = Array.from(select.querySelectorAll('option')).map((o) => o.textContent)
      expect(names).toEqual(['None', 'Maple Street', 'Minivan'])
      expect(screen.queryByTestId('asset-role-select')).not.toBeInTheDocument()
    })

    it('shows nothing when the family has no assets', async () => {
      vi.mocked(getAssets).mockResolvedValue([])
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await screen.findByTestId('expense-amount-input')
      await waitFor(() => expect(getAssets).toHaveBeenCalled())
      expect(screen.queryByTestId('asset-link-select')).not.toBeInTheDocument()
    })

    it('sends the asset and a role when one is chosen', async () => {
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await fillAmount()
      await selectAsset('asset-house')
      expect(screen.getByTestId('asset-role-select')).toHaveValue('maintenance')
      await userEvent.selectOptions(screen.getByTestId('asset-role-select'), 'improvement')
      await userEvent.click(screen.getByTestId('expense-submit-btn'))
      await waitFor(() =>
        expect(createExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          expect.objectContaining({ asset_id: 'asset-house', asset_role: 'improvement' })
        )
      )
    })

    it('sends no link fields when no asset is chosen', async () => {
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await fillAmount()
      await userEvent.click(screen.getByTestId('expense-submit-btn'))
      await waitFor(() => expect(createExpense).toHaveBeenCalled())
      expect(vi.mocked(createExpense).mock.calls[0][1]).not.toHaveProperty('asset_id')
      expect(vi.mocked(createExpense).mock.calls[0][1]).not.toHaveProperty('asset_role')
    })

    it('hides the asset picker for income and never links it', async () => {
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await fillAmount()
      await selectAsset('asset-house')
      await userEvent.click(screen.getByLabelText('Income'))
      expect(screen.queryByTestId('asset-link-select')).not.toBeInTheDocument()
      await userEvent.click(screen.getByTestId('expense-submit-btn'))
      await waitFor(() => expect(createExpense).toHaveBeenCalled())
      expect(vi.mocked(createExpense).mock.calls[0][1]).not.toHaveProperty('asset_id')
    })

    it('names the asset and role selects by their labels', async () => {
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await selectAsset('asset-house')
      expect(screen.getByLabelText('Asset')).toHaveValue('asset-house')
      expect(screen.getByLabelText(/^Counts as/)).toHaveValue('maintenance')
    })

    it('re-derives the default role when Repeat is toggled, until the role is picked by hand', async () => {
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await selectAsset('asset-house')
      const role = screen.getByTestId('asset-role-select')
      expect(role).toHaveValue('maintenance')
      await userEvent.click(screen.getByTestId('repeat-checkbox'))
      expect(role).toHaveValue('loan_payment')
      await userEvent.click(screen.getByTestId('repeat-checkbox'))
      expect(role).toHaveValue('maintenance')

      await userEvent.selectOptions(role, 'improvement')
      await userEvent.click(screen.getByTestId('repeat-checkbox'))
      expect(role).toHaveValue('improvement')
    })

    it('passes the link to the recurring entry when set to repeat', async () => {
      wrap(<CreateExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await fillAmount()
      await userEvent.click(screen.getByTestId('repeat-checkbox'))
      await selectAsset('asset-house')
      // A repeating entry on an asset with a loan is most likely the loan payment.
      expect(screen.getByTestId('asset-role-select')).toHaveValue('loan_payment')
      await userEvent.click(screen.getByTestId('expense-submit-btn'))
      await waitFor(() =>
        expect(createRecurringExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          expect.objectContaining({ asset_id: 'asset-house', asset_role: 'loan_payment' })
        )
      )
    })
  })

  describe('EditExpenseDialog', () => {
    function renderEdit(expense: Expense) {
      wrap(<EditExpenseDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} expense={expense} />)
    }

    it('preselects the linked asset and role', async () => {
      renderEdit(makeExpense({ asset_id: 'asset-house', asset_role: 'improvement' }))
      await waitFor(() =>
        expect(screen.getByTestId('asset-link-select')).toHaveValue('asset-house')
      )
      expect(screen.getByTestId('asset-role-select')).toHaveValue('improvement')
    })

    it('keeps offering the linked asset after it is sold', async () => {
      renderEdit(makeExpense({ asset_id: 'asset-boat', asset_role: 'maintenance' }))
      await waitFor(() => expect(screen.getByTestId('asset-link-select')).toHaveValue('asset-boat'))
    })

    it('does not resend an unchanged link', async () => {
      renderEdit(makeExpense({ asset_id: 'asset-house', asset_role: 'improvement' }))
      await waitFor(() =>
        expect(screen.getByTestId('asset-link-select')).toHaveValue('asset-house')
      )
      await userEvent.click(screen.getByRole('button', { name: /save/i }))
      await waitFor(() => expect(updateExpense).toHaveBeenCalled())
      expect(vi.mocked(updateExpense).mock.calls[0][2]).not.toHaveProperty('asset_id')
    })

    it('unlinks with explicit nulls', async () => {
      renderEdit(makeExpense({ asset_id: 'asset-house', asset_role: 'improvement' }))
      await waitFor(() =>
        expect(screen.getByTestId('asset-link-select')).toHaveValue('asset-house')
      )
      await userEvent.selectOptions(screen.getByTestId('asset-link-select'), '')
      await userEvent.click(screen.getByRole('button', { name: /save/i }))
      await waitFor(() =>
        expect(updateExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          'exp-1',
          expect.objectContaining({ asset_id: null, asset_role: null })
        )
      )
    })

    it('switches to a different asset and role', async () => {
      renderEdit(makeExpense())
      await selectAsset('asset-car')
      await userEvent.selectOptions(screen.getByTestId('asset-role-select'), 'carrying_cost')
      await userEvent.click(screen.getByRole('button', { name: /save/i }))
      await waitFor(() =>
        expect(updateExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          'exp-1',
          expect.objectContaining({ asset_id: 'asset-car', asset_role: 'carrying_cost' })
        )
      )
    })

    it('unlinks a linked entry that is changed to income', async () => {
      renderEdit(makeExpense({ asset_id: 'asset-house', asset_role: 'improvement' }))
      await waitFor(() =>
        expect(screen.getByTestId('asset-link-select')).toHaveValue('asset-house')
      )
      await userEvent.click(screen.getByLabelText('Income'))
      expect(screen.queryByTestId('asset-link-select')).not.toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: /save/i }))
      await waitFor(() =>
        expect(updateExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          'exp-1',
          expect.objectContaining({ asset_id: null, asset_role: null, entry_type: 'income' })
        )
      )
    })
  })

  describe('CreateRecurringDialog', () => {
    it('defaults to loan_payment on an asset with a loan and sends the link', async () => {
      wrap(<CreateRecurringDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await userEvent.type(await screen.findByTestId('recurring-amount-input'), '1970')
      await selectAsset('asset-house')
      expect(screen.getByTestId('asset-role-select')).toHaveValue('loan_payment')
      await waitFor(() => expect(screen.getByTestId('recurring-submit-btn')).toBeEnabled())
      await userEvent.click(screen.getByTestId('recurring-submit-btn'))
      await waitFor(() =>
        expect(createRecurringExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          expect.objectContaining({ asset_id: 'asset-house', asset_role: 'loan_payment' })
        )
      )
    })

    it('defaults to maintenance on an asset without a loan', async () => {
      wrap(<CreateRecurringDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await selectAsset('asset-car')
      expect(screen.getByTestId('asset-role-select')).toHaveValue('maintenance')
    })

    it('hides the picker for recurring income', async () => {
      wrap(<CreateRecurringDialog open onOpenChange={vi.fn()} familyId={FAMILY_ID} />)
      await screen.findByTestId('asset-link-select')
      await userEvent.click(screen.getByLabelText('Income'))
      expect(screen.queryByTestId('asset-link-select')).not.toBeInTheDocument()
    })
  })

  describe('EditRecurringDialog', () => {
    it('preselects the link and changes it', async () => {
      wrap(
        <EditRecurringDialog
          open
          onOpenChange={vi.fn()}
          familyId={FAMILY_ID}
          rule={makeRule({ asset_id: 'asset-house', asset_role: 'loan_payment' })}
        />
      )
      await waitFor(() =>
        expect(screen.getByTestId('asset-link-select')).toHaveValue('asset-house')
      )
      expect(screen.getByTestId('asset-role-select')).toHaveValue('loan_payment')
      await userEvent.selectOptions(screen.getByTestId('asset-role-select'), 'carrying_cost')
      await userEvent.click(screen.getByTestId('edit-recurring-save'))
      await waitFor(() =>
        expect(updateRecurringExpense).toHaveBeenCalledWith(
          FAMILY_ID,
          'rule-1',
          expect.objectContaining({ asset_id: 'asset-house', asset_role: 'carrying_cost' })
        )
      )
    })

    it('unlinks with explicit nulls', async () => {
      wrap(
        <EditRecurringDialog
          open
          onOpenChange={vi.fn()}
          familyId={FAMILY_ID}
          rule={makeRule({ asset_id: 'asset-house', asset_role: 'loan_payment' })}
        />
      )
      await waitFor(() =>
        expect(screen.getByTestId('asset-link-select')).toHaveValue('asset-house')
      )
      await userEvent.selectOptions(screen.getByTestId('asset-link-select'), '')
      await userEvent.click(screen.getByTestId('edit-recurring-save'))
      await waitFor(() =>
        expect(updateRecurringExpense).toHaveBeenCalledWith(FAMILY_ID, 'rule-1', {
          asset_id: null,
          asset_role: null,
        })
      )
    })

    it('has no asset picker for an income rule', async () => {
      wrap(
        <EditRecurringDialog
          open
          onOpenChange={vi.fn()}
          familyId={FAMILY_ID}
          rule={makeRule({ entry_type: 'income', category_id: null })}
        />
      )
      await screen.findByTestId('edit-recurring-amount')
      expect(screen.queryByTestId('asset-link-select')).not.toBeInTheDocument()
    })
  })
})
