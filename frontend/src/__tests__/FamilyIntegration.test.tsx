/**
 * Frontend integration test: family creation and member display flow.
 *
 * Exercises the end-to-end family creation flow:
 *   1. User with no family visits /family → CreateFamilyView renders with form
 *   2. User fills in family name and submits the form
 *   3. createFamily API returns the new family; currentUser query is invalidated
 *   4. /api/me now returns user with family → FamilyDashboard renders
 *   5. getFamily returns family details with the creator as admin member
 *   6. FamilyDashboardView renders with the member list showing the creator
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import FamilyPage from '../pages/FamilyPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'

// ---------------------------------------------------------------------------
// Mock the family API module — we control all responses in each test
// ---------------------------------------------------------------------------

vi.mock('../api/family', () => ({
  createFamily: vi.fn(),
  getFamily: vi.fn(),
  getPendingInvites: vi.fn(),
  sendInvite: vi.fn(),
  removeMember: vi.fn(),
  changeRole: vi.fn(),
  leaveFamily: vi.fn(),
  respondToInvite: vi.fn(),
}))

import { createFamily, getFamily, getPendingInvites } from '../api/family'

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const USER_ID = 'user-integration-1'
const FAMILY_ID = 'fam-integration-1'

const userWithoutFamily = {
  id: USER_ID,
  email: 'creator@example.com',
  display_name: 'Alice Creator',
  avatar_url: null,
  timezone: 'America/New_York',
  family: null,
}

const userWithFamily = {
  ...userWithoutFamily,
  family: {
    id: FAMILY_ID,
    name: 'The Integration Family',
    role: 'admin' as const,
  },
}

const createdFamily = {
  id: FAMILY_ID,
  name: 'The Integration Family',
  timezone: 'America/New_York',
  created_by: USER_ID,
  created_at: '2026-01-01T00:00:00Z',
  members: [
    {
      user_id: USER_ID,
      family_id: FAMILY_ID,
      email: 'creator@example.com',
      display_name: 'Alice Creator',
      avatar_url: null,
      role: 'admin' as const,
      joined_at: '2026-01-01T00:00:00Z',
    },
  ],
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderFamilyPage() {
  // gcTime: 0 so cached currentUser is GC'd when component unmounts, forcing
  // a fresh fetch after family creation (simulating real cache invalidation).
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 0,
      },
    },
  })

  return render(
    <MemoryRouter initialEntries={['/family']}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <FamilyProvider>
            <Routes>
              <Route path="/family" element={<FamilyPage />} />
            </Routes>
          </FamilyProvider>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('Family integration: create family and view member dashboard', () => {
  let meCallCount: number
  let originalFetch: typeof globalThis.fetch

  beforeEach(() => {
    vi.clearAllMocks()
    meCallCount = 0
    originalFetch = globalThis.fetch

    // Intercept /api/me: first call returns user without family,
    // subsequent calls return user with family (after creation).
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : (input as Request).url

      if (url.includes('/api/me')) {
        meCallCount++
        const payload = meCallCount === 1 ? userWithoutFamily : userWithFamily
        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      if (url.includes('/api/auth/refresh')) {
        return new Response(null, { status: 401 })
      }

      return new Response(null, { status: 404 })
    }) as typeof fetch

    // getPendingInvites returns empty list (not relevant to this flow)
    vi.mocked(getPendingInvites).mockResolvedValue([])
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('shows Create Family form when user has no family', async () => {
    renderFamilyPage()

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /create your family/i })).toBeInTheDocument()
    })

    expect(screen.getByPlaceholderText(/the smiths/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create family/i })).toBeInTheDocument()
  })

  it('create family flow: form → API call → dashboard with creator as admin', async () => {
    // createFamily resolves with the new family record
    vi.mocked(createFamily).mockResolvedValue(createdFamily)

    // getFamily resolves with full details including member list
    vi.mocked(getFamily).mockResolvedValue(createdFamily)

    renderFamilyPage()

    // ── Step 1: Verify CreateFamilyView renders ──────────────────────────
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /create your family/i })).toBeInTheDocument()
    })

    // ── Step 2: Fill in the family name field ────────────────────────────
    const nameInput = screen.getByPlaceholderText(/the smiths/i)
    fireEvent.change(nameInput, { target: { value: 'The Integration Family' } })

    // Submit button should now be enabled
    const submitButton = screen.getByRole('button', { name: /create family/i })
    expect(submitButton).not.toBeDisabled()

    // ── Step 3: Submit the form ──────────────────────────────────────────
    const form = nameInput.closest('form')!
    fireEvent.submit(form)

    // ── Step 4: createFamily API was called with correct args ────────────
    await waitFor(() => {
      expect(createFamily).toHaveBeenCalledWith('The Integration Family', 'America/New_York')
    })

    // ── Step 5: After creation, /api/me returns user with family.
    //    FamilyPage switches from CreateFamilyView to FamilyDashboardView.
    //    FamilyDashboardView calls getFamily and renders the member list.
    await waitFor(
      () => {
        expect(screen.getByText('The Integration Family')).toBeInTheDocument()
      },
      { timeout: 3000 }
    )

    // ── Step 6: Member list shows the creator as Owner/Admin ─────────────
    await waitFor(() => {
      expect(screen.getByText('Alice Creator (you)')).toBeInTheDocument()
    })

    // Creator is the owner — MemberList shows "Owner" badge for them
    expect(screen.getByText('Owner')).toBeInTheDocument()

    // Confirm the Members section heading is visible
    expect(screen.getByRole('heading', { name: /members/i })).toBeInTheDocument()
  })

  it('submit button is disabled when family name is blank', async () => {
    renderFamilyPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create family/i })).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /create family/i })).toBeDisabled()
  })
})
