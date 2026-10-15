import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import AssetDetailPage from '../pages/AssetDetailPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'
import type { AssetDetail } from '../types/asset'
import type { Expense } from '../types/expenses'

vi.mock('../hooks/useAuth', () => ({ useAuth: vi.fn() }))

vi.mock('../api/assets', () => ({
  getAsset: vi.fn(),
  getAssetHistory: vi.fn(),
  getAssetExpenses: vi.fn(),
  updateAsset: vi.fn(),
  deleteAsset: vi.fn(),
  sellAsset: vi.fn(),
  unsellAsset: vi.fn(),
  upsertLoan: vi.fn(),
  deleteLoan: vi.fn(),
  addCorrection: vi.fn(),
  deleteCorrection: vi.fn(),
  addValuation: vi.fn(),
  deleteValuation: vi.fn(),
  addContribution: vi.fn(),
  updateContribution: vi.fn(),
  deleteContribution: vi.fn(),
}))

vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

import { useAuth } from '../hooks/useAuth'
import {
  addCorrection,
  addValuation,
  deleteAsset,
  deleteValuation,
  getAsset,
  getAssetExpenses,
  getAssetHistory,
  sellAsset,
  unsellAsset,
} from '../api/assets'

const FAMILY_ID = 'fam-123'

function makeDetail(overrides: Partial<AssetDetail> = {}): AssetDetail {
  return {
    id: 'asset-1',
    family_id: FAMILY_ID,
    created_by_user_id: 'user-1',
    name: 'Maple Street',
    asset_type: 'house',
    purchase_date: '2021-06-01',
    purchase_price_cents: 40000000,
    down_payment_cents: 8000000,
    closing_costs_cents: 600000,
    address_line1: '12 Maple St',
    city: 'Raleigh',
    state: 'NC',
    zip_code: '27601',
    annual_depreciation_rate: null,
    sold_date: null,
    sale_price_cents: null,
    selling_costs_cents: null,
    is_sold: false,
    created_at: '2021-06-01T00:00:00Z',
    updated_at: '2021-06-01T00:00:00Z',
    loan: {
      id: 'loan-1',
      asset_id: 'asset-1',
      original_amount_cents: 32000000,
      annual_interest_rate: 0.0625,
      term_months: 360,
      first_payment_date: '2021-08-01',
      monthly_payment_cents: null,
      escrow_monthly_cents: 45000,
      computed_monthly_payment_cents: 197041,
      payoff_date_estimate: '2051-07-01',
      created_at: '',
      updated_at: '',
    },
    corrections: [
      {
        id: 'cor-1',
        loan_id: 'loan-1',
        as_of_date: '2024-01-01',
        balance_cents: 29000000,
        created_at: '',
      },
    ],
    valuations: [
      {
        id: 'val-1',
        asset_id: 'asset-1',
        as_of_date: '2025-05-01',
        value_cents: 46000000,
        note: 'Appraisal',
        created_at: '',
      },
    ],
    contributions: [
      {
        id: 'con-1',
        asset_id: 'asset-1',
        contribution_date: '2019-01-01',
        amount_cents: 1200000,
        role: 'improvement',
        description: 'New roof',
        created_at: '',
      },
    ],
    summary: {
      market_value_cents: 45000000,
      loan_balance_cents: 30000000,
      equity_cents: 15000000,
      cash_in_cents: 12000000,
      valuation_source: 'fhfa_zip3',
      down_payment_cents: 8000000,
      principal_paid_cents: 2000000,
      improvements_cents: 1200000,
      interest_paid_cents: 3000000,
      escrow_paid_cents: 900000,
      closing_costs_cents: 600000,
      maintenance_cents: 150000,
      carrying_cost_cents: 0,
      equity_building_cents: 11200000,
      sunk_cost_cents: 4650000,
      net_gain_cents: null,
    },
    valuation: { source: 'fhfa_zip3', label: 'FHFA ZIP3 276 · 2026Q2' },
    hpi_status: { latest_year: 2026, latest_quarter: 2 },
    ...overrides,
  }
}

function makeExpense(overrides: Partial<Expense> = {}): Expense {
  return {
    id: 'exp-1',
    family_id: FAMILY_ID,
    category: { id: 'cat-1', name: 'Housing', icon: '🏠' },
    created_by_user: { id: 'user-1', display_name: 'User' },
    amount_cents: 850000,
    description: 'Water heater',
    expense_date: '2026-03-10',
    created_at: '',
    updated_at: '',
    entry_type: 'expense',
    is_starting_balance: false,
    receipt_id: null,
    receipt_status: null,
    asset_id: 'asset-1',
    asset_role: 'improvement',
    ...overrides,
  }
}

function setRole(role: 'admin' | 'member') {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: 'user-1',
      email: 'u@example.com',
      display_name: 'User',
      avatar_url: null,
      timezone: 'UTC',
      family: { id: FAMILY_ID, name: 'Fam', role },
    },
    isLoading: false,
    isAuthenticated: true,
    logout: vi.fn(),
  } as unknown as ReturnType<typeof useAuth>)
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/assets/asset-1']}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <FamilyProvider>
            <Routes>
              <Route path="/assets/:assetId" element={<AssetDetailPage />} />
              <Route path="/assets" element={<div data-testid="assets-route" />} />
            </Routes>
          </FamilyProvider>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

describe('AssetDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setRole('admin')
    vi.mocked(getAsset).mockResolvedValue(makeDetail())
    vi.mocked(getAssetHistory).mockResolvedValue({
      points: [
        {
          date: '2025-01-31',
          market_value_cents: 44000000,
          loan_balance_cents: 30500000,
          equity_cents: 13500000,
          cash_in_cents: 11000000,
        },
        {
          date: '2025-02-28',
          market_value_cents: 45000000,
          loan_balance_cents: 30000000,
          equity_cents: 15000000,
          cash_in_cents: 12000000,
        },
      ],
    })
    vi.mocked(getAssetExpenses).mockResolvedValue([makeExpense()])
  })

  it('shows the name, headline numbers and the valuation disclaimer', async () => {
    renderPage()
    expect(await screen.findByTestId('asset-detail-name')).toHaveTextContent('Maple Street')
    expect(screen.getByTestId('asset-detail-value')).toHaveTextContent('$450,000')
    expect(screen.getByTestId('asset-detail-loan')).toHaveTextContent('$300,000')
    expect(screen.getByTestId('asset-detail-equity')).toHaveTextContent('$150,000')
    expect(screen.getByTestId('asset-detail-cash-in')).toHaveTextContent('$120,000')
    expect(screen.getByTestId('asset-valuation-note')).toHaveTextContent(
      'Estimate from FHFA regional index (as of 2026Q2) — not an appraisal.'
    )
  })

  it('renders the story chart once history loads', async () => {
    renderPage()
    // The chart is a lazy chunk; the first import can be slow on a busy machine.
    expect(await screen.findByTestId('story-chart', {}, { timeout: 10000 })).toBeInTheDocument()
  })

  it('splits cash in between equity-building and sunk cost', async () => {
    renderPage()
    const equity = await screen.findByTestId('breakdown-equity-building')
    expect(equity).toHaveTextContent('$112,000')
    expect(equity).toHaveTextContent('Down payment')
    expect(equity).toHaveTextContent('Principal paid')
    expect(equity).toHaveTextContent('Improvements')
    const sunk = screen.getByTestId('breakdown-sunk-cost')
    expect(sunk).toHaveTextContent('$46,500')
    expect(sunk).toHaveTextContent('Interest paid')
    expect(sunk).toHaveTextContent('Escrow')
  })

  it('degrades to dashes when the numbers are not available yet', async () => {
    vi.mocked(getAsset).mockResolvedValue(
      makeDetail({ summary: null, valuation: null, hpi_status: null })
    )
    vi.mocked(getAssetHistory).mockRejectedValue(new Error('nope'))
    renderPage()
    expect(await screen.findByTestId('asset-detail-value')).toHaveTextContent('—')
    expect(screen.queryByTestId('breakdown-equity-building')).not.toBeInTheDocument()
    expect(screen.queryByTestId('asset-valuation-note')).not.toBeInTheDocument()
  })

  it('shows the loan terms, computed payment and payoff estimate', async () => {
    renderPage()
    const loan = await screen.findByTestId('asset-loan-section')
    expect(loan).toHaveTextContent('6.25%')
    expect(loan).toHaveTextContent('30 years')
    expect(loan).toHaveTextContent('$1,970')
    expect(loan).toHaveTextContent('Jul 1, 2051')
    expect(within(loan).getByTestId('correction-row-cor-1')).toHaveTextContent('$290,000')
  })

  it('lists values, past spending and linked expenses', async () => {
    renderPage()
    expect(await screen.findByTestId('valuation-row-val-1')).toHaveTextContent('$460,000')
    expect(screen.getByTestId('contribution-row-con-1')).toHaveTextContent('New roof')
    const expense = await screen.findByTestId('asset-expense-row-exp-1')
    expect(expense).toHaveTextContent('Water heater')
    expect(expense).toHaveTextContent('Improvement')
    expect(expense).toHaveTextContent('$8,500')
  })

  it('shows members the numbers without any admin controls', async () => {
    setRole('member')
    renderPage()
    expect(await screen.findByTestId('asset-detail-name')).toBeInTheDocument()
    expect(screen.getByTestId('valuation-row-val-1')).toBeInTheDocument()
    for (const id of [
      'asset-edit-btn',
      'sell-btn',
      'delete-asset-btn',
      'loan-edit-btn',
      'correction-add-btn',
      'correction-delete-cor-1',
      'valuation-add-btn',
      'valuation-delete-val-1',
      'contribution-add-btn',
      'contribution-edit-con-1',
      'contribution-delete-con-1',
    ]) {
      expect(screen.queryByTestId(id)).not.toBeInTheDocument()
    }
  })

  it('lets an admin add a manual value', async () => {
    vi.mocked(addValuation).mockResolvedValue({
      id: 'val-2',
      asset_id: 'asset-1',
      as_of_date: '2026-06-01',
      value_cents: 47550000,
      note: null,
      created_at: '',
    })
    renderPage()
    await userEvent.click(await screen.findByTestId('valuation-add-btn'))
    await userEvent.clear(await screen.findByTestId('valuation-date-input'))
    await userEvent.type(screen.getByTestId('valuation-date-input'), '2026-06-01')
    await userEvent.type(screen.getByTestId('valuation-value-input'), '475,500')
    await userEvent.click(screen.getByTestId('valuation-submit-btn'))
    await waitFor(() =>
      expect(addValuation).toHaveBeenCalledWith(FAMILY_ID, 'asset-1', {
        as_of_date: '2026-06-01',
        value_cents: 47550000,
        note: null,
      })
    )
  })

  it('lets an admin add a loan balance correction', async () => {
    vi.mocked(addCorrection).mockResolvedValue({
      id: 'cor-2',
      loan_id: 'loan-1',
      as_of_date: '2026-01-01',
      balance_cents: 28000000,
      created_at: '',
    })
    renderPage()
    await userEvent.click(await screen.findByTestId('correction-add-btn'))
    await userEvent.clear(await screen.findByTestId('correction-date-input'))
    await userEvent.type(screen.getByTestId('correction-date-input'), '2026-01-01')
    await userEvent.type(screen.getByTestId('correction-balance-input'), '280000')
    await userEvent.click(screen.getByTestId('correction-submit-btn'))
    await waitFor(() =>
      expect(addCorrection).toHaveBeenCalledWith(FAMILY_ID, 'asset-1', {
        as_of_date: '2026-01-01',
        balance_cents: 28000000,
      })
    )
  })

  it('asks before deleting a value', async () => {
    vi.mocked(deleteValuation).mockResolvedValue(undefined)
    renderPage()
    await userEvent.click(await screen.findByTestId('valuation-delete-val-1'))
    expect(deleteValuation).not.toHaveBeenCalled()
    await userEvent.click(await screen.findByTestId('confirm-dialog-confirm'))
    await waitFor(() => expect(deleteValuation).toHaveBeenCalledWith(FAMILY_ID, 'asset-1', 'val-1'))
  })

  it('marks an asset as sold with a sale price and costs', async () => {
    vi.mocked(sellAsset).mockResolvedValue(makeDetail({ is_sold: true }))
    renderPage()
    await userEvent.click(await screen.findByTestId('sell-btn'))
    await userEvent.clear(await screen.findByTestId('sell-date-input'))
    await userEvent.type(screen.getByTestId('sell-date-input'), '2026-09-01')
    await userEvent.type(screen.getByTestId('sell-price-input'), '480000')
    await userEvent.type(screen.getByTestId('sell-costs-input'), '28800')
    await userEvent.click(screen.getByTestId('sell-submit-btn'))
    await waitFor(() =>
      expect(sellAsset).toHaveBeenCalledWith(FAMILY_ID, 'asset-1', {
        sold_date: '2026-09-01',
        sale_price_cents: 48000000,
        selling_costs_cents: 2880000,
      })
    )
  })

  it('shows the sale and net gain for a sold asset, and lets an admin undo it', async () => {
    vi.mocked(getAsset).mockResolvedValue(
      makeDetail({
        is_sold: true,
        sold_date: '2026-09-01',
        sale_price_cents: 48000000,
        selling_costs_cents: 2880000,
        summary: { ...makeDetail().summary!, net_gain_cents: -1234500 },
      })
    )
    vi.mocked(unsellAsset).mockResolvedValue(makeDetail())
    renderPage()
    expect(await screen.findByTestId('asset-detail-net-gain')).toHaveTextContent('−$12,345')
    expect(screen.getByTestId('asset-sold-info')).toHaveTextContent('Sep 1, 2026')
    expect(screen.queryByTestId('sell-btn')).not.toBeInTheDocument()
    await userEvent.click(screen.getByTestId('unsell-btn'))
    await userEvent.click(await screen.findByTestId('confirm-dialog-confirm'))
    await waitFor(() => expect(unsellAsset).toHaveBeenCalledWith(FAMILY_ID, 'asset-1'))
  })

  it('deletes an asset after confirmation and returns to the list', async () => {
    vi.mocked(deleteAsset).mockResolvedValue(undefined)
    renderPage()
    await userEvent.click(await screen.findByTestId('delete-asset-btn'))
    await userEvent.click(await screen.findByTestId('confirm-dialog-confirm'))
    await waitFor(() => expect(deleteAsset).toHaveBeenCalledWith(FAMILY_ID, 'asset-1'))
    expect(await screen.findByTestId('assets-route')).toBeInTheDocument()
    // The deleted asset must not be refetched (it would 404).
    expect(getAsset).toHaveBeenCalledTimes(1)
    expect(getAssetExpenses).toHaveBeenCalledTimes(1)
  })

  it('offers to add a loan when the asset has none', async () => {
    vi.mocked(getAsset).mockResolvedValue(makeDetail({ loan: null, corrections: [] }))
    renderPage()
    expect(await screen.findByTestId('loan-add-btn')).toBeInTheDocument()
    expect(screen.queryByTestId('asset-detail-loan')).not.toBeInTheDocument()
  })

  it('says when the asset is not found', async () => {
    vi.mocked(getAsset).mockRejectedValue(new Error('Asset not found'))
    renderPage()
    expect(await screen.findByTestId('asset-detail-error')).toBeInTheDocument()
  })
})
