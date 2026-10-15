import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import AssetsPage from '../pages/AssetsPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'
import type { AssetListItem } from '../types/asset'

vi.mock('../hooks/useAuth', () => ({ useAuth: vi.fn() }))

vi.mock('../api/assets', () => ({
  getAssets: vi.fn(),
  createAsset: vi.fn(() => new Promise(() => {})),
}))

vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

import { useAuth } from '../hooks/useAuth'
import { getAssets } from '../api/assets'

const FAMILY_ID = 'fam-123'

function makeAsset(overrides: Partial<AssetListItem> = {}): AssetListItem {
  return {
    id: 'asset-1',
    family_id: FAMILY_ID,
    created_by_user_id: 'user-1',
    name: 'Maple Street',
    asset_type: 'house',
    purchase_date: '2021-06-01',
    purchase_price_cents: 40000000,
    down_payment_cents: 8000000,
    closing_costs_cents: 0,
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
    has_loan: true,
    summary: {
      market_value_cents: 45000000,
      loan_balance_cents: 30000000,
      equity_cents: 15000000,
      cash_in_cents: 12000000,
      valuation_source: 'fhfa_zip3',
    },
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
    <MemoryRouter>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <FamilyProvider>
            <AssetsPage />
          </FamilyProvider>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

describe('AssetsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setRole('admin')
  })

  it('shows an empty state when there are no assets', async () => {
    vi.mocked(getAssets).mockResolvedValue([])
    renderPage()
    expect(await screen.findByTestId('assets-empty')).toBeInTheDocument()
  })

  it('shows value, loan, equity and cash in on each card, linking to the detail page', async () => {
    vi.mocked(getAssets).mockResolvedValue([makeAsset()])
    renderPage()
    const card = await screen.findByTestId('asset-card-asset-1')
    expect(card).toHaveTextContent('Maple Street')
    expect(card).toHaveTextContent('Raleigh, NC')
    expect(within(card).getByTestId('asset-value-asset-1')).toHaveTextContent('$450,000')
    expect(within(card).getByTestId('asset-loan-asset-1')).toHaveTextContent('$300,000')
    expect(within(card).getByTestId('asset-equity-asset-1')).toHaveTextContent('$150,000')
    expect(within(card).getByTestId('asset-cash-in-asset-1')).toHaveTextContent('$120,000')
    expect(card.closest('a')).toHaveAttribute('href', '/assets/asset-1')
  })

  it('shows a dash for numbers that are not available yet', async () => {
    vi.mocked(getAssets).mockResolvedValue([makeAsset({ summary: null })])
    renderPage()
    expect(await screen.findByTestId('asset-value-asset-1')).toHaveTextContent('—')
  })

  it('hides the loan figure for an asset without a loan balance', async () => {
    vi.mocked(getAssets).mockResolvedValue([
      makeAsset({
        summary: {
          market_value_cents: 1000000,
          loan_balance_cents: 0,
          equity_cents: 1000000,
          cash_in_cents: 900000,
          valuation_source: 'depreciation',
        },
      }),
    ])
    renderPage()
    await screen.findByTestId('asset-card-asset-1')
    expect(screen.queryByTestId('asset-loan-asset-1')).not.toBeInTheDocument()
  })

  it('shows negative equity with a minus sign', async () => {
    vi.mocked(getAssets).mockResolvedValue([
      makeAsset({
        summary: {
          market_value_cents: 20000000,
          loan_balance_cents: 25000000,
          equity_cents: -5000000,
          cash_in_cents: 9000000,
          valuation_source: 'fhfa_zip3',
        },
      }),
    ])
    renderPage()
    expect(await screen.findByTestId('asset-equity-asset-1')).toHaveTextContent('−$50,000')
  })

  it('puts sold assets in their own section', async () => {
    vi.mocked(getAssets).mockResolvedValue([
      makeAsset(),
      makeAsset({
        id: 'asset-2',
        name: 'Old Civic',
        asset_type: 'vehicle',
        is_sold: true,
        sold_date: '2025-02-01',
      }),
    ])
    renderPage()
    const sold = await screen.findByTestId('assets-sold-list')
    expect(within(sold).getByTestId('asset-card-asset-2')).toBeInTheDocument()
    expect(within(screen.getByTestId('assets-list')).queryByTestId('asset-card-asset-2')).toBeNull()
    expect(within(sold).getByTestId('asset-card-asset-2')).toHaveTextContent('Sold')
  })

  it('lets an admin add an asset', async () => {
    vi.mocked(getAssets).mockResolvedValue([])
    renderPage()
    await userEvent.click(await screen.findByTestId('add-asset-btn'))
    expect(await screen.findByTestId('asset-name-input')).toBeInTheDocument()
  })

  it('hides the add button from members', async () => {
    setRole('member')
    vi.mocked(getAssets).mockResolvedValue([makeAsset()])
    renderPage()
    await screen.findByTestId('asset-card-asset-1')
    expect(screen.queryByTestId('add-asset-btn')).not.toBeInTheDocument()
  })
})
