import type { AssetDetail, AssetHistoryPoint, AssetListItem, AssetRole } from '@/types/asset'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Parse a dollar amount typed by a person ("1,234.56") into integer cents; null if invalid. */
export function parseDollarsToCents(input: string): number | null {
  const cleaned = input.replace(/[$,\s]/g, '')
  if (!/^(\d+\.?\d{0,2}|\.\d{1,2})$/.test(cleaned)) return null
  return Math.round(parseFloat(cleaned) * 100)
}

/** Integer cents as the text shown in an editable amount field. */
export function centsToInput(cents: number): string {
  return String(cents / 100)
}

/** A percent typed by a person ("6.25") as a rate (0.0625) with at most `decimals` places. */
export function percentToRate(input: string, decimals: number): number | null {
  const trimmed = input.trim()
  if (!/^(\d+\.?\d*|\.\d+)$/.test(trimmed)) return null
  return Number((parseFloat(trimmed) / 100).toFixed(decimals))
}

/** A rate (0.0625) as the percent text shown in a field ("6.25"). */
export function rateToPercent(rate: number): string {
  return String(Number((rate * 100).toFixed(4)))
}

/** Whole-dollar money with a real minus sign, since equity and net gain can go negative. */
export function formatMoney(cents: number): string {
  const abs = Math.abs(cents) / 100
  const text =
    '$' + abs.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })
  return cents < 0 && Math.round(abs) !== 0 ? `−${text}` : text
}

function parseIso(isoDate: string): [number, number, number] {
  const [year, month, day] = isoDate.split('-').map(Number)
  return [year, month, day]
}

/** "2024-03-01" -> "Mar 1, 2024", parsed by hand so the timezone can't shift the day. */
export function formatDateLabel(isoDate: string): string {
  const [year, month, day] = parseIso(isoDate)
  return `${MONTHS[month - 1]} ${day}, ${year}`
}

/** "2025-03-31" -> "Mar '25". */
export function formatMonthLabel(isoDate: string): string {
  const [year, month] = parseIso(isoDate)
  return `${MONTHS[month - 1]} '${String(year).slice(2)}`
}

export function todayString(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

export interface ChartRow {
  date: string
  marketValue: number
  loanBalance: number
  equity: number
  cashIn: number
}

/** History points in dollars for the story chart (display only, never fed back to the API). */
export function toChartData(points: AssetHistoryPoint[]): ChartRow[] {
  return points.map((p) => ({
    date: p.date,
    marketValue: p.market_value_cents / 100,
    loanBalance: p.loan_balance_cents / 100,
    equity: p.equity_cents / 100,
    cashIn: p.cash_in_cents / 100,
  }))
}

const DEFAULT_DEPRECIATION_RATE = 0.15

/** The note under the headline numbers saying where the market value comes from. */
export function valuationDisclaimer(asset: AssetDetail): string | null {
  const source = asset.valuation?.source ?? asset.summary?.valuation_source
  if (!source) return null
  switch (source) {
    case 'fhfa_zip3':
    case 'fhfa_state': {
      const { latest_year: year, latest_quarter: quarter } = asset.hpi_status ?? {}
      const asOf = year && quarter ? ` (as of ${year}Q${quarter})` : ''
      return `Estimate from FHFA regional index${asOf} — not an appraisal.`
    }
    case 'manual': {
      const label = asset.valuation?.label
      return `Based on a value you entered${label ? ` (${label})` : ''}.`
    }
    case 'depreciation': {
      const percent = Number(
        ((asset.annual_depreciation_rate ?? DEFAULT_DEPRECIATION_RATE) * 100).toFixed(2)
      )
      return `Estimated from ${percent}% yearly depreciation — not an appraisal.`
    }
    case 'purchase_price':
      return 'No market data yet, so this uses the purchase price. Add a value to improve it.'
    default:
      return null
  }
}

/** Role to preselect when an expense is linked to `asset`: the loan payment is the usual recurring entry on a loan. */
export function defaultAssetRole(
  asset: Pick<AssetListItem, 'has_loan'>,
  recurring: boolean
): AssetRole {
  return recurring && asset.has_loan ? 'loan_payment' : 'maintenance'
}
