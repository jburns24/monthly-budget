import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import FamilyPage from '../pages/FamilyPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'

// Mock useAuth to control auth + family state
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

// Mock family API to prevent real HTTP calls
vi.mock('../api/family', () => ({
  createFamily: vi.fn(() => new Promise(() => {})),
  getFamily: vi.fn(() => new Promise(() => {})),
  getPendingInvites: vi.fn(() => new Promise(() => {})),
  sendInvite: vi.fn(() => new Promise(() => {})),
  removeMember: vi.fn(() => new Promise(() => {})),
  changeRole: vi.fn(() => new Promise(() => {})),
  leaveFamily: vi.fn(() => new Promise(() => {})),
  respondToInvite: vi.fn(() => new Promise(() => {})),
}))

import { useAuth } from '../hooks/useAuth'

function renderFamilyPage(initialPath = '/family') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
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

describe('FamilyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders CreateFamilyView when user has no family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: '1',
        email: 'a@b.com',
        display_name: 'Alice',
        avatar_url: null,
        timezone: 'UTC',
        family: null,
      },
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderFamilyPage()

    expect(screen.getByRole('heading', { name: /create your family/i })).toBeInTheDocument()
  })

  it('renders FamilyDashboardView (loading state) when user has a family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: '1',
        email: 'a@b.com',
        display_name: 'Alice',
        avatar_url: null,
        timezone: 'UTC',
        family: { id: 'fam-123', name: 'The Smiths', role: 'admin' },
      },
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderFamilyPage()

    // CreateFamilyView heading should NOT be shown when user has family
    expect(screen.queryByRole('heading', { name: /create your family/i })).not.toBeInTheDocument()
  })

  it('shows the create family form fields when no family', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: '1',
        email: 'a@b.com',
        display_name: 'Alice',
        avatar_url: null,
        timezone: 'UTC',
        family: null,
      },
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderFamilyPage()

    expect(screen.getByPlaceholderText(/the smiths/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create family/i })).toBeInTheDocument()
  })
})
