import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import { ProtectedRoute } from '../components/ProtectedRoute'
import Header from '../components/Header'
import system from '../theme'

// Mock useAuth so we control auth state in tests
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../hooks/useAuth'

const mockLogout = vi.fn().mockResolvedValue(undefined)

function renderWithProviders(ui: React.ReactElement, initialPath = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLogout.mockResolvedValue(undefined)
  })

  it('shows spinner while auth is loading', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isLoading: true,
      isAuthenticated: false,
      logout: mockLogout,
    })

    renderWithProviders(
      <Routes>
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    )

    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('redirects to /login when unauthenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      logout: mockLogout,
    })

    renderWithProviders(
      <Routes>
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    )

    expect(screen.getByText('Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('renders children when authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '1', email: 'a@b.com', display_name: 'Alice', avatar_url: null, timezone: 'UTC' },
      isLoading: false,
      isAuthenticated: true,
      logout: mockLogout,
    })

    renderWithProviders(
      <Routes>
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <div>Protected Content</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    )

    expect(screen.getByText('Protected Content')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })
})

describe('Header', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockLogout.mockResolvedValue(undefined)
  })

  it('renders nothing when user is null', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      isLoading: false,
      isAuthenticated: false,
      logout: mockLogout,
    })

    const { container } = renderWithProviders(
      <Routes>
        <Route path="/" element={<Header />} />
      </Routes>
    )

    expect(container.firstChild).toBeNull()
  })

  it('shows user display name when authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: '1',
        email: 'a@b.com',
        display_name: 'Alice Smith',
        avatar_url: null,
        timezone: 'UTC',
      },
      isLoading: false,
      isAuthenticated: true,
      logout: mockLogout,
    })

    renderWithProviders(
      <Routes>
        <Route path="/" element={<Header />} />
      </Routes>
    )

    expect(screen.getByText('Alice Smith')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument()
  })

  it('shows user initials when avatar_url is null', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: '1',
        email: 'a@b.com',
        display_name: 'Alice Smith',
        avatar_url: null,
        timezone: 'UTC',
      },
      isLoading: false,
      isAuthenticated: true,
      logout: mockLogout,
    })

    renderWithProviders(
      <Routes>
        <Route path="/" element={<Header />} />
      </Routes>
    )

    expect(screen.getByText('AS')).toBeInTheDocument()
  })

  it('calls logout and navigates to /login on sign out click', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '1', email: 'a@b.com', display_name: 'Alice', avatar_url: null, timezone: 'UTC' },
      isLoading: false,
      isAuthenticated: true,
      logout: mockLogout,
    })

    renderWithProviders(
      <Routes>
        <Route path="/" element={<Header />} />
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    )

    fireEvent.click(screen.getByRole('button', { name: /sign out/i }))

    await waitFor(() => {
      expect(mockLogout).toHaveBeenCalledOnce()
    })
    await waitFor(() => {
      expect(screen.getByText('Login Page')).toBeInTheDocument()
    })
  })
})
