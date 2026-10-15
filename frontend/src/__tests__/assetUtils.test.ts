import { describe, it, expect } from 'vitest'
import {
  centsToInput,
  defaultAssetRole,
  formatDateLabel,
  formatMonthLabel,
  formatMoney,
  parseDollarsToCents,
  percentToRate,
  rateToPercent,
  toChartData,
  valuationDisclaimer,
} from '../utils/assets'
import type { AssetDetail } from '../types/asset'

describe('parseDollarsToCents', () => {
  it('parses plain and decorated dollar amounts to integer cents', () => {
    expect(parseDollarsToCents('1500')).toBe(150000)
    expect(parseDollarsToCents('$1,234.56')).toBe(123456)
    expect(parseDollarsToCents('0.1')).toBe(10)
    expect(parseDollarsToCents('.5')).toBe(50)
  })

  it('avoids float drift', () => {
    expect(parseDollarsToCents('19.99')).toBe(1999)
    expect(parseDollarsToCents('1.15')).toBe(115)
  })

  it('returns null for empty, negative or malformed input', () => {
    expect(parseDollarsToCents('')).toBeNull()
    expect(parseDollarsToCents('abc')).toBeNull()
    expect(parseDollarsToCents('-5')).toBeNull()
    expect(parseDollarsToCents('1.234')).toBeNull()
  })
})

describe('percent <-> rate', () => {
  it('converts a percent to a rate rounded to the given decimals', () => {
    expect(percentToRate('6.25', 5)).toBe(0.0625)
    expect(percentToRate('12.3', 4)).toBe(0.123)
    expect(percentToRate('15', 4)).toBe(0.15)
  })

  it('returns null for blank or invalid percents', () => {
    expect(percentToRate('', 4)).toBeNull()
    expect(percentToRate('x', 4)).toBeNull()
    expect(percentToRate('-1', 4)).toBeNull()
  })

  it('shows a rate as a clean percent string', () => {
    expect(rateToPercent(0.0625)).toBe('6.25')
    expect(rateToPercent(0.15)).toBe('15')
    expect(rateToPercent(0.123)).toBe('12.3')
  })
})

describe('formatting', () => {
  it('formats money with a real minus sign for negatives', () => {
    expect(formatMoney(123400)).toBe('$1,234')
    expect(formatMoney(-123400)).toBe('−$1,234')
    expect(formatMoney(0)).toBe('$0')
  })

  it('formats an ISO date without timezone drift', () => {
    expect(formatDateLabel('2024-03-01')).toBe('Mar 1, 2024')
  })

  it('formats a month label without timezone drift', () => {
    expect(formatMonthLabel('2025-03-01')).toBe("Mar '25")
  })

  it('renders cents as an editable dollar string', () => {
    expect(centsToInput(150000)).toBe('1500')
    expect(centsToInput(123456)).toBe('1234.56')
  })
})

describe('toChartData', () => {
  it('maps history points to dollar values', () => {
    const rows = toChartData([
      {
        date: '2025-01-31',
        market_value_cents: 30000000,
        loan_balance_cents: 24000000,
        equity_cents: 6000000,
        cash_in_cents: 7000050,
      },
    ])
    expect(rows).toEqual([
      {
        date: '2025-01-31',
        marketValue: 300000,
        loanBalance: 240000,
        equity: 60000,
        cashIn: 70000.5,
      },
    ])
  })
})

function makeDetail(overrides: Partial<AssetDetail> = {}): AssetDetail {
  return {
    id: 'a1',
    family_id: 'f1',
    created_by_user_id: 'u1',
    name: 'Home',
    asset_type: 'house',
    purchase_date: '2020-01-01',
    purchase_price_cents: 30000000,
    down_payment_cents: 6000000,
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

describe('valuationDisclaimer', () => {
  it('cites the FHFA index quarter for an index estimate', () => {
    const text = valuationDisclaimer(
      makeDetail({
        valuation: { source: 'fhfa_zip3', label: 'FHFA ZIP3 276 · 2026Q2' },
        hpi_status: { latest_year: 2026, latest_quarter: 2 },
      })
    )
    expect(text).toBe('Estimate from FHFA regional index (as of 2026Q2) — not an appraisal.')
  })

  it('omits the quarter when the status is unknown', () => {
    expect(
      valuationDisclaimer(makeDetail({ valuation: { source: 'fhfa_state', label: null } }))
    ).toBe('Estimate from FHFA regional index — not an appraisal.')
  })

  it('explains manual values, depreciation and the purchase price fallback', () => {
    expect(
      valuationDisclaimer(makeDetail({ valuation: { source: 'manual', label: 'Jun 1, 2026' } }))
    ).toMatch(/value you entered/i)
    expect(
      valuationDisclaimer(
        makeDetail({
          asset_type: 'vehicle',
          annual_depreciation_rate: 0.2,
          valuation: { source: 'depreciation', label: null },
        })
      )
    ).toMatch(/20%/)
    expect(
      valuationDisclaimer(makeDetail({ valuation: { source: 'purchase_price', label: null } }))
    ).toMatch(/purchase price/i)
  })

  it('returns null when there is no valuation info', () => {
    expect(valuationDisclaimer(makeDetail())).toBeNull()
  })
})

describe('defaultAssetRole', () => {
  it('prefers loan_payment for a recurring entry on an asset with a loan', () => {
    expect(defaultAssetRole({ has_loan: true }, true)).toBe('loan_payment')
  })

  it('falls back to maintenance without a loan or for one-off expenses', () => {
    expect(defaultAssetRole({ has_loan: false }, true)).toBe('maintenance')
    expect(defaultAssetRole({ has_loan: true }, false)).toBe('maintenance')
  })
})
