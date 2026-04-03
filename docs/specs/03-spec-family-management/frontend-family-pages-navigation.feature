# Source: docs/specs/03-spec-family-management/03-spec-family-management.md
# Pattern: Web/UI
# Recommended test type: E2E

Feature: Frontend — Family Pages & Navigation

  Scenario: Bottom navigation renders with correct tabs
    Given the user is logged in and viewing any protected page
    Then a bottom navigation bar is visible with tabs "Home", "Categories", "Family", and "Settings"
    And the currently active tab is visually highlighted

  Scenario: Family tab navigates to /family route
    Given the user is logged in and viewing the home page
    When the user taps the "Family" tab in the bottom navigation
    Then the page navigates to /family

  Scenario: Create Family form displays when user has no family
    Given the user is logged in and has no family
    When the user navigates to /family
    Then a "Create Family" form is displayed
    And the form contains a family name input field
    And the form contains a timezone selector
    And the form contains a "Create" button

  Scenario: Create Family form submits and shows family dashboard
    Given the user is logged in and has no family
    And the user is on the /family page viewing the "Create Family" form
    When the user enters "Burns Household" in the name field and selects a timezone and clicks "Create"
    Then the page transitions to the family dashboard view
    And the family name "Burns Household" is displayed
    And the current user appears in the member list with role "Admin"

  Scenario: Family dashboard displays member list with roles
    Given the user is logged in and belongs to a family with two members
    When the user navigates to /family
    Then the family name is displayed at the top
    And a member list is shown with each member's name and role badge
    And the admin members show an "Admin" badge
    And the regular members show a "Member" badge

  Scenario: Admin sees invite section on family dashboard
    Given the user is logged in as an admin of a family
    When the user navigates to /family
    Then an "Invite Member" section is visible
    And the section contains an email input field and a "Send" button

  Scenario: Non-admin does not see invite section
    Given the user is logged in as a regular member of a family
    When the user navigates to /family
    Then no "Invite Member" section is visible

  Scenario: Invite form shows generic success toast on submit
    Given the user is logged in as an admin on the /family page
    When the user enters "someone@example.com" in the invite email field and clicks "Send"
    Then a toast message appears with text "If a user with that email exists, they will receive an invitation."

  Scenario: Pending invites are displayed with accept and decline buttons
    Given the user is logged in and has two pending family invitations
    When the user views the pending invites section
    Then two invitation entries are displayed with the inviting family's name
    And each invitation has an "Accept" button and a "Decline" button

  Scenario: Accepting an invite joins the family and refreshes the view
    Given the user is logged in and has a pending invite to family "Burns Household"
    When the user clicks "Accept" on that invitation
    Then the pending invite disappears
    And the family dashboard for "Burns Household" is displayed
    And the user appears in the member list

  Scenario: Declining an invite removes it from the list
    Given the user is logged in and has a pending invite
    When the user clicks "Decline" on that invitation
    Then the invitation is removed from the pending invites list

  Scenario: Admin can change a member's role with confirmation
    Given the user is logged in as an admin on the /family page
    And the family has a member with role "Member"
    When the user selects "Admin" from the role control for that member
    Then a confirmation dialog appears asking to confirm the role change
    When the user confirms the dialog
    Then the member's role badge updates to "Admin"

  Scenario: Admin can remove a member with confirmation
    Given the user is logged in as an admin on the /family page
    And the family has a non-owner member
    When the user clicks "Remove Member" for that member
    Then a confirmation dialog appears asking to confirm removal
    When the user confirms the dialog
    Then the member is removed from the member list

  Scenario: Non-owner member can leave family
    Given the user is logged in as a non-owner member on the /family page
    When the user clicks "Leave Family"
    Then a confirmation dialog appears
    When the user confirms the dialog
    Then the page transitions to the "Create Family" form
    And the user is no longer a member of the family

  Scenario: FamilyContext provides family ID and role to child components
    Given the user is logged in and belongs to a family with role "admin"
    When a child component accesses the FamilyContext
    Then the context provides the family ID matching the user's family
    And the context provides the role "admin"
