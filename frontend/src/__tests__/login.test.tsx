import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import LoginPage from '../pages/LoginPage'
import AuthCallbackPage from '../pages/AuthCallbackPage'
import system from '../theme'

// Mock the auth API module to prevent real HTTP calls during tests
vi.mock('../api/auth', () => ({
  postAuthCallback: vi.fn(() => new Promise(() => {})),
}))

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

describe('LoginPage', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  it('renders the app name heading', () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    )
    expect(screen.getByRole('heading', { name: /monthly budget/i })).toBeInTheDocument()
  })

  it('renders the "Sign in with Google" button', () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<LoginPage />} />
      </Routes>
    )
    expect(screen.getByRole('button', { name: /sign in with google/i })).toBeInTheDocument()
  })
})

describe('AuthCallbackPage — error states', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
  })

  it('shows error when Google returns an error param', () => {
    renderWithProviders(
      <Routes>
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
      </Routes>,
      '/auth/callback?error=access_denied'
    )
    expect(screen.getByText(/cancelled or denied/i)).toBeInTheDocument()
  })

  it('shows error when state is missing from URL', () => {
    renderWithProviders(
      <Routes>
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
      </Routes>,
      '/auth/callback?code=abc123'
    )
    expect(screen.getByText(/missing authorization code or state/i)).toBeInTheDocument()
  })

  it('shows error when state does not match sessionStorage', () => {
    sessionStorage.setItem('oauth_state', 'correct-state')
    sessionStorage.setItem('pkce_code_verifier', 'some-verifier')

    renderWithProviders(
      <Routes>
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
      </Routes>,
      '/auth/callback?code=abc123&state=wrong-state'
    )
    expect(screen.getByText(/state mismatch/i)).toBeInTheDocument()
  })

  it('shows loading spinner when callback params are valid (API in-flight)', () => {
    sessionStorage.setItem('oauth_state', 'valid-state')
    sessionStorage.setItem('pkce_code_verifier', 'valid-verifier')

    renderWithProviders(
      <Routes>
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
      </Routes>,
      '/auth/callback?code=auth-code&state=valid-state'
    )
    expect(screen.getByText(/signing you in/i)).toBeInTheDocument()
  })
})
