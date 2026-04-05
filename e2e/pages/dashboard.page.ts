/**
 * Page Object Model for the dashboard / home page (/).
 */
import { Page, Locator } from '@playwright/test'

export class DashboardPage {
  readonly page: Page

  // Month selector controls
  readonly prevMonthButton: Locator
  readonly nextMonthButton: Locator
  readonly monthLabel: Locator

  // Budget summary
  readonly totalSpent: Locator

  // Category cards
  readonly categoryCards: Locator

  // FAB (Floating Action Button)
  readonly fabButton: Locator

  // Expense form inputs (in CreateExpenseDialog opened via FAB)
  readonly amountInput: Locator
  readonly descriptionInput: Locator
  readonly categorySelect: Locator
  readonly dateInput: Locator
  readonly submitButton: Locator

  // Dialog root
  readonly dialogRoot: Locator

  constructor(page: Page) {
    this.page = page

    this.prevMonthButton = page.getByRole('button', { name: /previous month/i })
    this.nextMonthButton = page.getByRole('button', { name: /next month/i })
    // The dashboard renders month as a Heading inside the month selector flex
    this.monthLabel = page.getByRole('heading').filter({ hasText: /\w+ \d{4}/ })

    // Total spent value — identified by data-testid
    this.totalSpent = page.getByTestId('total-spent')

    // Category cards are rendered as role="button" with aria-label "{name} category"
    this.categoryCards = page.locator('[role="button"][aria-label$=" category"]')

    this.fabButton = page.getByTestId('fab-add-expense')

    // Expense dialog form fields (same as CreateExpenseDialog)
    this.amountInput = page.getByTestId('expense-amount-input')
    this.descriptionInput = page.getByTestId('expense-description-input')
    this.categorySelect = page.getByTestId('expense-category-select')
    this.dateInput = page.getByTestId('expense-date-input')
    this.submitButton = page.getByTestId('expense-submit-btn')

    this.dialogRoot = page.locator('[role="dialog"]')
  }

  async goto(): Promise<void> {
    await this.page.goto('/')
  }

  /**
   * Open the Add Expense dialog via the FAB.
   */
  async openCreateDialogViaFab(): Promise<void> {
    await this.fabButton.click()
  }

  /**
   * Navigate to the previous month.
   */
  async goToPrevMonth(): Promise<void> {
    await this.prevMonthButton.click()
  }

  /**
   * Navigate to the next month.
   */
  async goToNextMonth(): Promise<void> {
    await this.nextMonthButton.click()
  }

  /**
   * Click a category card by its name to navigate to the filtered expenses view.
   */
  async clickCategoryCard(categoryName: string): Promise<void> {
    await this.page.getByRole('button', { name: `${categoryName} category` }).click()
  }

  /**
   * Return the locator for a specific category card by name.
   */
  categoryCard(categoryName: string): Locator {
    return this.page.getByRole('button', { name: `${categoryName} category` })
  }

  /**
   * Return the progress indicator (aria-label with "% of budget used") for a
   * given category card.  Expects the card to be in the DOM.
   */
  categoryProgressIndicator(categoryName: string): Locator {
    return this.categoryCard(categoryName).locator('[aria-label$="% of budget used"]')
  }
}
