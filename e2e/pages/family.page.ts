/**
 * Page Object Model for the family page (/family).
 */
import { Page, Locator } from '@playwright/test'

export class FamilyPage {
  readonly page: Page

  // Create-family form
  readonly createFamilyForm: Locator
  readonly familyNameInput: Locator
  readonly createSubmitButton: Locator

  // Dashboard
  readonly familyDashboard: Locator
  readonly memberList: Locator

  // Invite form
  readonly inviteEmailInput: Locator
  readonly inviteSubmitButton: Locator

  // Pending invites
  readonly pendingInvitesList: Locator

  constructor(page: Page) {
    this.page = page

    this.createFamilyForm = page.getByRole('heading', { name: /create your family/i })
    this.familyNameInput = page.getByPlaceholder(/e\.g\. the smiths/i)
    this.createSubmitButton = page.getByRole('button', { name: /create family/i })

    this.familyDashboard = page.getByRole('heading', { level: 1 })
    this.memberList = page.getByRole('list').first()

    this.inviteEmailInput = page.getByPlaceholder(/email address/i)
    this.inviteSubmitButton = page.getByRole('button', { name: /send invite/i })

    this.pendingInvitesList = page.getByTestId('pending-invites')
  }

  async goto(): Promise<void> {
    await this.page.goto('/family')
  }

  async createFamily(name: string): Promise<void> {
    await this.familyNameInput.fill(name)
    await this.createSubmitButton.click()
  }

  async sendInvite(email: string): Promise<void> {
    await this.inviteEmailInput.fill(email)
    await this.inviteSubmitButton.click()
  }

  async acceptInvite(): Promise<void> {
    await this.page.getByRole('button', { name: /accept/i }).first().click()
  }

  async declineInvite(): Promise<void> {
    await this.page.getByRole('button', { name: /decline/i }).first().click()
  }

  /** Returns true when the family dashboard is visible (user is in a family). */
  async hasDashboard(): Promise<boolean> {
    // The dashboard renders the family name as an h1; the create form is shown otherwise
    const heading = this.page.getByRole('heading', { level: 1 })
    return heading.isVisible()
  }

  /** Returns true when the create-family form is visible. */
  async hasCreateForm(): Promise<boolean> {
    return this.createFamilyForm.isVisible()
  }

  /** Returns the text content of each member card/list-item. */
  async getMemberTexts(): Promise<string[]> {
    const items = await this.page.getByRole('listitem').all()
    return Promise.all(items.map((item) => item.innerText()))
  }
}
