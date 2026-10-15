import type { Expense } from './expenses'

export type AssetType = 'house' | 'vehicle' | 'other'
export type ContributionRole = 'improvement' | 'maintenance' | 'carrying_cost'
export type AssetRole = 'loan_payment' | ContributionRole

export const ASSET_TYPE_LABELS: Record<AssetType, string> = {
  house: 'House',
  vehicle: 'Vehicle',
  other: 'Other',
}

export const ASSET_TYPE_ICONS: Record<AssetType, string> = {
  house: '🏠',
  vehicle: '🚗',
  other: '📦',
}

export const ASSET_ROLE_LABELS: Record<AssetRole, string> = {
  loan_payment: 'Loan payment',
  improvement: 'Improvement',
  maintenance: 'Maintenance',
  carrying_cost: 'Carrying cost',
}

export const ASSET_ROLE_HINTS: Record<AssetRole, string> = {
  loan_payment: 'Tracked from the loan schedule, so it only counts toward your budget.',
  improvement: 'Adds value, like a new roof or kitchen.',
  maintenance: 'Keeps it running, like repairs and servicing.',
  carrying_cost: 'Costs of owning it, like insurance and property tax.',
}

export const CONTRIBUTION_ROLES: ContributionRole[] = [
  'improvement',
  'maintenance',
  'carrying_cost',
]

/** Where the current market value comes from. */
export type ValuationSource =
  | 'manual'
  | 'fhfa_zip3'
  | 'fhfa_state'
  | 'depreciation'
  | 'purchase_price'
  | 'sale_price'

export interface AssetListSummary {
  market_value_cents: number
  loan_balance_cents: number
  equity_cents: number
  cash_in_cents: number
  valuation_source: ValuationSource | string
}

export interface AssetDetailSummary extends AssetListSummary {
  down_payment_cents: number
  principal_paid_cents: number
  improvements_cents: number
  interest_paid_cents: number
  escrow_paid_cents: number
  closing_costs_cents: number
  maintenance_cents: number
  carrying_cost_cents: number
  equity_building_cents: number
  sunk_cost_cents: number
  /** Only once the asset is sold. */
  net_gain_cents: number | null
}

export interface AssetValuationInfo {
  source: ValuationSource | string
  label: string | null
}

export interface HpiStatus {
  latest_year: number | null
  latest_quarter: number | null
}

export interface Asset {
  id: string
  family_id: string
  created_by_user_id: string
  name: string
  asset_type: AssetType
  purchase_date: string
  purchase_price_cents: number
  down_payment_cents: number
  closing_costs_cents: number
  address_line1: string | null
  city: string | null
  state: string | null
  zip_code: string | null
  /** 0.15 = 15%. Null means the default applies (vehicles only). */
  annual_depreciation_rate: number | null
  sold_date: string | null
  sale_price_cents: number | null
  selling_costs_cents: number | null
  is_sold: boolean
  created_at: string
  updated_at: string
}

export interface AssetListItem extends Asset {
  has_loan: boolean
  summary: AssetListSummary | null
}

export interface AssetLoan {
  id: string
  asset_id: string
  original_amount_cents: number
  /** 0.0625 = 6.25% */
  annual_interest_rate: number
  term_months: number
  first_payment_date: string
  /** Stored override of the P&I payment; null means computed from the formula. */
  monthly_payment_cents: number | null
  escrow_monthly_cents: number
  computed_monthly_payment_cents: number | null
  payoff_date_estimate: string | null
  created_at: string
  updated_at: string
}

export interface LoanCorrection {
  id: string
  loan_id: string
  as_of_date: string
  balance_cents: number
  created_at: string
}

export interface AssetValuation {
  id: string
  asset_id: string
  as_of_date: string
  value_cents: number
  note: string | null
  created_at: string
}

export interface AssetContribution {
  id: string
  asset_id: string
  contribution_date: string
  amount_cents: number
  role: ContributionRole
  description: string
  created_at: string
}

export interface AssetDetail extends Asset {
  loan: AssetLoan | null
  corrections: LoanCorrection[]
  valuations: AssetValuation[]
  contributions: AssetContribution[]
  summary: AssetDetailSummary | null
  valuation: AssetValuationInfo | null
  hpi_status: HpiStatus | null
}

export interface AssetHistoryPoint {
  /** ISO date, month-end. */
  date: string
  market_value_cents: number
  loan_balance_cents: number
  equity_cents: number
  cash_in_cents: number
}

export interface AssetHistory {
  points: AssetHistoryPoint[]
}

export interface AssetListResponse {
  assets: AssetListItem[]
}

export interface AssetExpensesResponse {
  expenses: Expense[]
}

export interface AssetLoanInput {
  original_amount_cents: number
  annual_interest_rate: number
  term_months: number
  first_payment_date: string
  monthly_payment_cents: number | null
  escrow_monthly_cents: number
}

export interface AssetCreate {
  name: string
  asset_type: AssetType
  purchase_date: string
  purchase_price_cents: number
  down_payment_cents?: number
  closing_costs_cents?: number
  address_line1?: string | null
  city?: string | null
  state?: string | null
  zip_code?: string | null
  annual_depreciation_rate?: number | null
  loan?: AssetLoanInput | null
}

export type AssetUpdate = Partial<Omit<AssetCreate, 'loan'>>

export interface AssetSell {
  sold_date: string
  sale_price_cents: number
  selling_costs_cents: number
}

export interface LoanCorrectionCreate {
  as_of_date: string
  balance_cents: number
}

export interface AssetValuationCreate {
  as_of_date: string
  value_cents: number
  note?: string | null
}

export interface AssetContributionCreate {
  contribution_date: string
  amount_cents: number
  role: ContributionRole
  description: string
}

export type AssetContributionUpdate = Partial<AssetContributionCreate>
