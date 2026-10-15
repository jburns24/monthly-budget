import type { AssetLoan, AssetLoanInput } from '@/types/asset'
import { centsToInput, parseDollarsToCents, percentToRate, rateToPercent } from '@/utils/assets'

export type TermUnit = 'years' | 'months'

/** The loan sub-form as typed text; parsed to an API payload only on submit. */
export interface LoanFormState {
  amount: string
  ratePct: string
  term: string
  termUnit: TermUnit
  firstPaymentDate: string
  /** Optional P&I override; blank means compute from the terms. */
  payment: string
  escrow: string
}

export function emptyLoanForm(firstPaymentDate = ''): LoanFormState {
  return {
    amount: '',
    ratePct: '',
    term: '30',
    termUnit: 'years',
    firstPaymentDate,
    payment: '',
    escrow: '',
  }
}

export function loanToForm(loan: AssetLoan): LoanFormState {
  const wholeYears = loan.term_months % 12 === 0
  return {
    amount: centsToInput(loan.original_amount_cents),
    ratePct: rateToPercent(loan.annual_interest_rate),
    term: String(wholeYears ? loan.term_months / 12 : loan.term_months),
    termUnit: wholeYears ? 'years' : 'months',
    firstPaymentDate: loan.first_payment_date,
    payment: loan.monthly_payment_cents == null ? '' : centsToInput(loan.monthly_payment_cents),
    escrow: loan.escrow_monthly_cents ? centsToInput(loan.escrow_monthly_cents) : '',
  }
}

/** The API payload for the form, or null while any field is missing or invalid. */
export function loanFormToInput(form: LoanFormState): AssetLoanInput | null {
  const amount = parseDollarsToCents(form.amount)
  const rate = percentToRate(form.ratePct, 5)
  const termValue = /^\d+$/.test(form.term.trim()) ? Number(form.term.trim()) : 0
  const termMonths = form.termUnit === 'years' ? termValue * 12 : termValue
  const payment = form.payment.trim() ? parseDollarsToCents(form.payment) : null
  const escrow = form.escrow.trim() ? parseDollarsToCents(form.escrow) : 0

  if (!amount || amount <= 0) return null
  if (rate === null || rate > 1) return null
  if (termMonths <= 0 || termMonths > 1200) return null
  if (!form.firstPaymentDate) return null
  if (form.payment.trim() && !payment) return null
  if (escrow === null) return null

  return {
    original_amount_cents: amount,
    annual_interest_rate: rate,
    term_months: termMonths,
    first_payment_date: form.firstPaymentDate,
    monthly_payment_cents: payment,
    escrow_monthly_cents: escrow,
  }
}
