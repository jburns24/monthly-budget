/**
 * Page Object Model for the expenses page (/expenses).
 */
import { Page, Locator } from '@playwright/test'

export class ExpensesPage {
  readonly page: Page

  // Header actions
  readonly addExpenseButton: Locator

  // FAB (Floating Action Button)
  readonly fabButton: Locator

  // Month selector controls
  readonly prevMonthButton: Locator
  readonly nextMonthButton: Locator
  readonly monthDisplay: Locator

  // Category filter
  readonly categoryFilterSelect: Locator

  // Expense form inputs (in CreateExpenseDialog / EditExpenseDialog)
  readonly amountInput: Locator
  readonly descriptionInput: Locator
  readonly categorySelect: Locator
  readonly dateInput: Locator
  readonly submitButton: Locator

  // Expense list
  readonly expenseList: Locator
  readonly expenseListEmpty: Locator
  readonly editButtons: Locator
  readonly deleteButtons: Locator

  // Pagination controls
  readonly paginationControls: Locator
  readonly prevPageButton: Locator
  readonly nextPageButton: Locator
  readonly pageIndicator: Locator

  // Dialog root
  readonly dialogRoot: Locator

  constructor(page: Page) {
    this.page = page

    this.addExpenseButton = page.getByTestId('add-expense-btn')
    this.fabButton = page.getByTestId('fab-add-expense')

    this.prevMonthButton = page.getByTestId('prev-month-btn')
    this.nextMonthButton = page.getByTestId('next-month-btn')
    this.monthDisplay = page.getByTestId('month-display')

    this.categoryFilterSelect = page.getByTestId('category-filter-select')

    this.amountInput = page.getByTestId('expense-amount-input')
    this.descriptionInput = page.getByTestId('expense-description-input')
    this.categorySelect = page.getByTestId('expense-category-select')
    this.dateInput = page.getByTestId('expense-date-input')
    this.submitButton = page.getByTestId('expense-submit-btn')

    this.expenseList = page.getByTestId('expense-list')
    this.expenseListEmpty = page.getByTestId('expense-list-empty')
    this.editButtons = page.locator('[data-testid^="expense-edit-btn-"]')
    this.deleteButtons = page.locator('[data-testid^="expense-delete-btn-"]')

    this.paginationControls = page.getByTestId('pagination-controls')
    this.prevPageButton = page.getByTestId('prev-page-btn')
    this.nextPageButton = page.getByTestId('next-page-btn')
    this.pageIndicator = page.getByTestId('page-indicator')

    this.dialogRoot = page.locator('[role="dialog"]')
  }

  async goto(): Promise<void> {
    await this.page.goto('/expenses')
  }

  /**
   * Open the Add Expense dialog via the header button.
   */
  async openCreateDialog(): Promise<void> {
    await this.addExpenseButton.click()
  }

  /**
   * Open the Add Expense dialog via the FAB.
   */
  async openCreateDialogViaFab(): Promise<void> {
    await this.fabButton.click()
  }

  /**
   * Fill in and submit the expense form.
   * Assumes the dialog is already open.
   */
  async fillExpenseForm(opts: {
    amount: string
    description?: string
    categoryId?: string
    date?: string
  }): Promise<void> {
    await this.amountInput.fill(opts.amount)
    if (opts.description !== undefined) {
      await this.descriptionInput.fill(opts.description)
    }
    if (opts.categoryId !== undefined) {
      await this.categorySelect.selectOption(opts.categoryId)
    }
    if (opts.date !== undefined) {
      await this.dateInput.fill(opts.date)
    }
    await this.submitButton.click()
  }

  /**
   * Click the Edit button for an expense by its ID.
   */
  async editExpense(expenseId: string): Promise<void> {
    await this.page.getByTestId(`expense-edit-btn-${expenseId}`).click()
  }

  /**
   * Click the Delete button for an expense by its ID.
   */
  async deleteExpense(expenseId: string): Promise<void> {
    await this.page.getByTestId(`expense-delete-btn-${expenseId}`).click()
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
   * Select a category in the filter dropdown (pass '' for All Categories).
   */
  async filterByCategory(categoryId: string): Promise<void> {
    await this.categoryFilterSelect.selectOption(categoryId)
  }

  /**
   * Return the locator for a specific expense card by expense ID.
   */
  expenseCard(expenseId: string): Locator {
    return this.page.getByTestId(`expense-card-${expenseId}`)
  }

  /**
   * Return all currently visible expense cards.
   */
  get expenseCards(): Locator {
    return this.page.locator('[data-testid^="expense-card-"]')
  }
}
