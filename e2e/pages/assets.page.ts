/**
 * Page Objects for the assets list (/assets) and an asset's detail page (/assets/:id).
 */
import { Page, Locator } from '@playwright/test'

export interface HouseFormOptions {
  name: string
  state: string
  zip: string
  /** YYYY-MM-DD */
  purchaseDate: string
  /** Dollars, e.g. '400000' */
  price: string
  downPayment: string
  loan?: {
    amount: string
    /** Percent, e.g. '6.25' */
    ratePct: string
    /** YYYY-MM-DD */
    firstPaymentDate: string
  }
}

export class AssetsPage {
  readonly page: Page

  readonly addAssetButton: Locator

  // Asset form (create dialog)
  readonly nameInput: Locator
  readonly stateInput: Locator
  readonly zipInput: Locator
  readonly purchaseDateInput: Locator
  readonly priceInput: Locator
  readonly downPaymentInput: Locator
  readonly withLoanCheckbox: Locator
  readonly loanAmountInput: Locator
  readonly loanRateInput: Locator
  readonly loanFirstPaymentInput: Locator
  readonly submitButton: Locator

  constructor(page: Page) {
    this.page = page

    this.addAssetButton = page.getByTestId('add-asset-btn')

    this.nameInput = page.getByTestId('asset-name-input')
    this.stateInput = page.getByTestId('asset-state-input')
    this.zipInput = page.getByTestId('asset-zip-input')
    this.purchaseDateInput = page.getByTestId('asset-purchase-date-input')
    this.priceInput = page.getByTestId('asset-price-input')
    this.downPaymentInput = page.getByTestId('asset-down-payment-input')
    this.withLoanCheckbox = page.getByTestId('asset-with-loan-checkbox')
    this.loanAmountInput = page.getByTestId('loan-amount-input')
    this.loanRateInput = page.getByTestId('loan-rate-input')
    this.loanFirstPaymentInput = page.getByTestId('loan-first-payment-input')
    this.submitButton = page.getByTestId('asset-submit-btn')
  }

  async goto(): Promise<void> {
    await this.page.goto('/assets')
  }

  async openCreateDialog(): Promise<void> {
    await this.addAssetButton.click()
  }

  /** Fill and submit the add-asset form for a house (the default type). Assumes the dialog is open. */
  async createHouse(opts: HouseFormOptions): Promise<void> {
    await this.nameInput.fill(opts.name)
    await this.stateInput.fill(opts.state)
    await this.zipInput.fill(opts.zip)
    await this.purchaseDateInput.fill(opts.purchaseDate)
    await this.priceInput.fill(opts.price)
    await this.downPaymentInput.fill(opts.downPayment)
    if (opts.loan) {
      await this.withLoanCheckbox.check()
      await this.loanAmountInput.fill(opts.loan.amount)
      await this.loanRateInput.fill(opts.loan.ratePct)
      await this.loanFirstPaymentInput.fill(opts.loan.firstPaymentDate)
    }
    await this.submitButton.click()
  }

  /** The list card for an asset, found by the name shown on it. */
  cardNamed(name: string): Locator {
    return this.page.locator('[data-testid^="asset-card-"]', { hasText: name })
  }
}

export class AssetDetailPage {
  readonly page: Page

  readonly name: Locator
  readonly value: Locator
  readonly loanBalance: Locator
  readonly equity: Locator
  readonly cashIn: Locator
  readonly equityBuilding: Locator
  readonly sunkCost: Locator
  readonly linkedExpenses: Locator

  constructor(page: Page) {
    this.page = page

    this.name = page.getByTestId('asset-detail-name')
    this.value = page.getByTestId('asset-detail-value')
    this.loanBalance = page.getByTestId('asset-detail-loan')
    this.equity = page.getByTestId('asset-detail-equity')
    this.cashIn = page.getByTestId('asset-detail-cash-in')
    this.equityBuilding = page.getByTestId('breakdown-equity-building')
    this.sunkCost = page.getByTestId('breakdown-sunk-cost')
    this.linkedExpenses = page.getByTestId('asset-expenses-list')
  }
}
