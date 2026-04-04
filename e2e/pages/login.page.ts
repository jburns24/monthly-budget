/**
 * Page Object Model for the login page (/login).
 */
import { Page, Locator } from '@playwright/test'

export class LoginPage {
  readonly page: Page
  readonly googleSignInButton: Locator

  constructor(page: Page) {
    this.page = page
    this.googleSignInButton = page.getByRole('button', { name: /sign in with google/i })
  }

  async goto(): Promise<void> {
    await this.page.goto('/login')
  }

  async isVisible(): Promise<boolean> {
    return this.googleSignInButton.isVisible()
  }
}
