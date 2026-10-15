import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import AssetFormDialog from '../components/assets/AssetFormDialog'
import system from '../theme'
import type { AssetDetail } from '../types/asset'

vi.mock('../api/assets', () => ({
  createAsset: vi.fn(),
  updateAsset: vi.fn(),
}))

vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

import { createAsset, updateAsset } from '../api/assets'

function makeDetail(overrides: Partial<AssetDetail> = {}): AssetDetail {
  return {
    id: 'asset-1',
    family_id: 'fam-1',
    created_by_user_id: 'u1',
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
    created_at: '',
    updated_at: '',
    loan: null,
    corrections: [],
    valuations: [],
    contributions: [],
    summary: null,
    valuation: null,
    hpi_status: null,
    ...overrides,
  }
}

function renderDialog(props: Partial<React.ComponentProps<typeof AssetFormDialog>> = {}) {
  const onClose = vi.fn()
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <AssetFormDialog familyId="fam-1" onClose={onClose} {...props} />
      </QueryClientProvider>
    </ChakraProvider>
  )
  return onClose
}

async function fill(testId: string, value: string) {
  const el = await screen.findByTestId(testId)
  await userEvent.clear(el)
  if (value) await userEvent.type(el, value)
}

// Each test types into many fields, which is slow on a busy machine.
vi.setConfig({ testTimeout: 20000 })

describe('AssetFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(createAsset).mockResolvedValue(makeDetail())
    vi.mocked(updateAsset).mockResolvedValue(makeDetail())
  })

  it('needs a state and ZIP before a house can be saved', async () => {
    renderDialog()
    await fill('asset-name-input', 'Maple Street')
    await fill('asset-price-input', '400000')
    expect(screen.getByTestId('asset-submit-btn')).toBeDisabled()
    await fill('asset-state-input', 'nc')
    await fill('asset-zip-input', '27601')
    expect(screen.getByTestId('asset-submit-btn')).toBeEnabled()
  })

  it('creates a house with its loan, sending integer cents and a decimal rate', async () => {
    const onClose = renderDialog()
    await fill('asset-name-input', 'Maple Street')
    await fill('asset-address-input', '12 Maple St')
    await fill('asset-city-input', 'Raleigh')
    await fill('asset-state-input', 'nc')
    await fill('asset-zip-input', '27601')
    await fill('asset-purchase-date-input', '2021-06-01')
    await fill('asset-price-input', '400,000')
    await fill('asset-down-payment-input', '80000')
    await userEvent.click(screen.getByTestId('asset-with-loan-checkbox'))
    await fill('loan-amount-input', '320000')
    await fill('loan-rate-input', '6.25')
    await fill('loan-first-payment-input', '2021-08-01')
    await fill('loan-escrow-input', '450.50')

    await userEvent.click(screen.getByTestId('asset-submit-btn'))

    await waitFor(() =>
      expect(createAsset).toHaveBeenCalledWith('fam-1', {
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
        loan: {
          original_amount_cents: 32000000,
          annual_interest_rate: 0.0625,
          term_months: 360,
          first_payment_date: '2021-08-01',
          monthly_payment_cents: null,
          escrow_monthly_cents: 45050,
        },
      })
    )
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('reads a loan term entered in months', async () => {
    renderDialog()
    await fill('asset-name-input', 'Cabin')
    await fill('asset-state-input', 'NC')
    await fill('asset-zip-input', '27601')
    await fill('asset-price-input', '100000')
    await userEvent.click(screen.getByTestId('asset-with-loan-checkbox'))
    await fill('loan-amount-input', '80000')
    await fill('loan-rate-input', '5')
    await userEvent.selectOptions(screen.getByTestId('loan-term-unit-select'), 'months')
    await fill('loan-term-input', '180')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))
    await waitFor(() => expect(createAsset).toHaveBeenCalled())
    expect(vi.mocked(createAsset).mock.calls[0][1].loan?.term_months).toBe(180)
  })

  it('blocks saving while the loan section is incomplete', async () => {
    renderDialog()
    await fill('asset-name-input', 'Cabin')
    await fill('asset-state-input', 'NC')
    await fill('asset-zip-input', '27601')
    await fill('asset-price-input', '100000')
    expect(screen.getByTestId('asset-submit-btn')).toBeEnabled()
    await userEvent.click(screen.getByTestId('asset-with-loan-checkbox'))
    expect(screen.getByTestId('asset-submit-btn')).toBeDisabled()
  })

  it('shows depreciation (default 15%) instead of address for a vehicle', async () => {
    renderDialog()
    await userEvent.selectOptions(await screen.findByTestId('asset-type-select'), 'vehicle')
    expect(screen.queryByTestId('asset-zip-input')).not.toBeInTheDocument()
    expect(screen.getByTestId('asset-depreciation-input')).toHaveValue('15')

    await fill('asset-name-input', 'Minivan')
    await fill('asset-price-input', '30000')
    await fill('asset-depreciation-input', '12.3')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))

    await waitFor(() => expect(createAsset).toHaveBeenCalled())
    const payload = vi.mocked(createAsset).mock.calls[0][1]
    expect(payload.asset_type).toBe('vehicle')
    expect(payload.annual_depreciation_rate).toBe(0.123)
    expect(payload).not.toHaveProperty('zip_code')
  })

  it('does not offer a loan section when editing, and saves with a PUT', async () => {
    const onClose = renderDialog({ asset: makeDetail() })
    expect(await screen.findByTestId('asset-name-input')).toHaveValue('Maple Street')
    expect(screen.getByTestId('asset-price-input')).toHaveValue('400000')
    expect(screen.queryByTestId('asset-with-loan-checkbox')).not.toBeInTheDocument()

    await fill('asset-name-input', 'Maple St house')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))

    await waitFor(() => expect(updateAsset).toHaveBeenCalled())
    expect(vi.mocked(updateAsset).mock.calls[0].slice(0, 2)).toEqual(['fam-1', 'asset-1'])
    expect(vi.mocked(updateAsset).mock.calls[0][2]).toMatchObject({ name: 'Maple St house' })
    expect(createAsset).not.toHaveBeenCalled()
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('gives every field an accessible name', async () => {
    renderDialog()
    for (const label of [
      /^Name/,
      /^Type/,
      /^Street address/,
      /^City/,
      /^State/,
      /^ZIP/,
      /^Purchase date/,
      /^Purchase price/,
      /^Down payment/,
      /^Closing costs/,
    ]) {
      expect(await screen.findByLabelText(label)).toBeInTheDocument()
    }
    await userEvent.click(screen.getByLabelText('This has a loan'))
    for (const label of [
      /^Loan amount/,
      /^Interest rate/,
      /^First payment date/,
      /^Monthly payment/,
      /^Escrow per month/,
      'Loan term length',
      'Loan term unit',
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
  })

  it('leaves an untouched default depreciation to the server when adding a vehicle', async () => {
    renderDialog()
    await userEvent.selectOptions(await screen.findByLabelText(/^Type/), 'vehicle')
    await fill('asset-name-input', 'Minivan')
    await fill('asset-price-input', '30000')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))
    await waitFor(() => expect(createAsset).toHaveBeenCalled())
    expect(vi.mocked(createAsset).mock.calls[0][1]).not.toHaveProperty('annual_depreciation_rate')
  })

  it('does not save the default rate on a vehicle edited without touching it', async () => {
    renderDialog({
      asset: makeDetail({
        asset_type: 'vehicle',
        annual_depreciation_rate: null,
        state: null,
        zip_code: null,
      }),
    })
    await fill('asset-name-input', 'Minivan 2')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))
    await waitFor(() => expect(updateAsset).toHaveBeenCalled())
    expect(vi.mocked(updateAsset).mock.calls[0][2]).not.toHaveProperty('annual_depreciation_rate')
  })

  it('sends a depreciation rate that was set', async () => {
    renderDialog({
      asset: makeDetail({
        asset_type: 'vehicle',
        annual_depreciation_rate: 0.2,
        state: null,
        zip_code: null,
      }),
    })
    expect(await screen.findByTestId('asset-depreciation-input')).toHaveValue('20')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))
    await waitFor(() => expect(updateAsset).toHaveBeenCalled())
    expect(vi.mocked(updateAsset).mock.calls[0][2]).toMatchObject({ annual_depreciation_rate: 0.2 })
  })

  it('clears the address when a house is changed to another type', async () => {
    renderDialog({ asset: makeDetail() })
    await userEvent.selectOptions(await screen.findByLabelText(/^Type/), 'other')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))
    await waitFor(() => expect(updateAsset).toHaveBeenCalled())
    expect(vi.mocked(updateAsset).mock.calls[0][2]).toMatchObject({
      asset_type: 'other',
      address_line1: null,
      city: null,
      state: null,
      zip_code: null,
    })
  })

  it('clears the depreciation rate when a vehicle is changed to a house', async () => {
    renderDialog({
      asset: makeDetail({
        asset_type: 'vehicle',
        annual_depreciation_rate: 0.2,
        state: null,
        zip_code: null,
      }),
    })
    await userEvent.selectOptions(await screen.findByLabelText(/^Type/), 'house')
    await fill('asset-state-input', 'NC')
    await fill('asset-zip-input', '27601')
    await userEvent.click(screen.getByTestId('asset-submit-btn'))
    await waitFor(() => expect(updateAsset).toHaveBeenCalled())
    expect(vi.mocked(updateAsset).mock.calls[0][2]).toMatchObject({
      asset_type: 'house',
      annual_depreciation_rate: null,
      state: 'NC',
    })
  })
})
