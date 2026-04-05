/**
 * Page Object Model for the categories page (/categories).
 */
import { Page, Locator } from '@playwright/test'

export class CategoriesPage {
  readonly page: Page

  // Header actions
  readonly addButton: Locator
  readonly seedButton: Locator

  // Dialog form inputs
  readonly categoryNameInput: Locator
  readonly iconInput: Locator
  readonly sortOrderInput: Locator
  readonly submitButton: Locator

  // Confirm delete dialog
  readonly confirmDeleteButton: Locator
  readonly dialogRoot: Locator

  // Category list
  readonly categoryListItems: Locator
  readonly editButtons: Locator
  readonly deleteButtons: Locator

  constructor(page: Page) {
    this.page = page

    this.addButton = page.getByRole('button', { name: /add category/i })
    this.seedButton = page.getByRole('button', { name: /seed/i })

    this.categoryNameInput = page.getByPlaceholder(/e\.g\. groceries/i)
    this.iconInput = page.getByPlaceholder(/e\.g\. 🛒/i)
    this.sortOrderInput = page.getByPlaceholder('0')
    this.submitButton = page.getByRole('button', { name: /create/i })

    this.confirmDeleteButton = page.getByRole('button', { name: /delete/i }).last()
    this.dialogRoot = page.locator('[role="dialog"]')

    this.categoryListItems = page.locator('[data-testid="category-item"]')
    this.editButtons = page.getByRole('button', { name: /^edit/i })
    this.deleteButtons = page.getByRole('button', { name: /^delete/i })
  }

  async goto(): Promise<void> {
    await this.page.goto('/categories')
  }

  async createCategory(name: string, icon?: string, sortOrder?: number): Promise<void> {
    await this.addButton.click()
    await this.categoryNameInput.fill(name)
    if (icon !== undefined) {
      await this.iconInput.fill(icon)
    }
    if (sortOrder !== undefined) {
      await this.sortOrderInput.fill(String(sortOrder))
    }
    await this.submitButton.click()
  }

  async editCategory(name: string): Promise<void> {
    await this.page.getByRole('button', { name: `Edit ${name}` }).click()
  }

  async deleteCategory(name: string): Promise<void> {
    await this.page.getByRole('button', { name: `Delete ${name}` }).click()
    await this.confirmDeleteButton.click()
  }

  async seedDefaults(): Promise<void> {
    await this.seedButton.click()
  }

  async getCategoryNames(): Promise<string[]> {
    // Category names are rendered as medium-weight text inside each list row.
    // We target the aria-label on the Edit buttons to derive category names,
    // or fall back to reading the text nodes directly.
    const editBtns = await this.editButtons.all()
    const names: string[] = []
    for (const btn of editBtns) {
      const label = await btn.getAttribute('aria-label')
      if (label) {
        // aria-label is "Edit {name}"
        names.push(label.replace(/^Edit\s+/i, ''))
      }
    }
    return names
  }
}
