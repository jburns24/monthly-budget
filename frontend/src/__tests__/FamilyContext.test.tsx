import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { FamilyProvider, useFamilyContext } from '../contexts/FamilyContext'

// Mock useAuth so we control what user/family data is returned
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../hooks/useAuth'

// Helper component that renders context values as text for easy assertion
function ContextConsumer() {
  const { familyId, role, family } = useFamilyContext()
  return (
    <div>
      <span data-testid="familyId">{familyId ?? 'null'}</span>
      <span data-testid="role">{role ?? 'null'}</span>
      <span data-testid="familyName">{family?.name ?? 'null'}</span>
    </div>
  )
}

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('FamilyContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('provides null values when user has no family', () => {
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

    renderWithProviders(
      <FamilyProvider>
        <ContextConsumer />
      </FamilyProvider>
    )

    expect(screen.getByTestId('familyId').textContent).toBe('null')
    expect(screen.getByTestId('role').textContent).toBe('null')
    expect(screen.getByTestId('familyName').textContent).toBe('null')
  })

  it('provides familyId and role when user belongs to a family', () => {
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

    renderWithProviders(
      <FamilyProvider>
        <ContextConsumer />
      </FamilyProvider>
    )

    expect(screen.getByTestId('familyId').textContent).toBe('fam-123')
    expect(screen.getByTestId('role').textContent).toBe('admin')
    expect(screen.getByTestId('familyName').textContent).toBe('The Smiths')
  })

  it('provides member role when user is a member (not admin)', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: '2',
        email: 'b@b.com',
        display_name: 'Bob',
        avatar_url: null,
        timezone: 'UTC',
        family: { id: 'fam-456', name: 'The Joneses', role: 'member' },
      },
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderWithProviders(
      <FamilyProvider>
        <ContextConsumer />
      </FamilyProvider>
    )

    expect(screen.getByTestId('familyId').textContent).toBe('fam-456')
    expect(screen.getByTestId('role').textContent).toBe('member')
    expect(screen.getByTestId('familyName').textContent).toBe('The Joneses')
  })

  it('provides null values when user is null (not authenticated)', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      logout: vi.fn().mockResolvedValue(undefined),
    })

    renderWithProviders(
      <FamilyProvider>
        <ContextConsumer />
      </FamilyProvider>
    )

    expect(screen.getByTestId('familyId').textContent).toBe('null')
    expect(screen.getByTestId('role').textContent).toBe('null')
    expect(screen.getByTestId('familyName').textContent).toBe('null')
  })
})
