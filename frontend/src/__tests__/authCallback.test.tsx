import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import AuthCallbackPage from '../pages/AuthCallbackPage'
import system from '../theme'

// Mock the auth API — each test sets its own resolved/rejected value
vi.mock('../api/auth', () => ({
  postAuthCallback: vi.fn(),
}))

import { postAuthCallback } from '../api/auth'

const mockMeUser = {
  id: 'user-1',
  email: 'user@example.com',
  display_name: 'Test User',
  avatar_url: null,
  timezone: 'UTC',
  family: null,
}

function renderCallback(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <Routes>
            <Route path="/auth/callback" element={<AuthCallbackPage />} />
            <Route path="/" element={<div>Home Page</div>} />
            <Route path="/login" element={<div>Login Page</div>} />
          </Routes>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

describe('AuthCallbackPage — success flow', () => {
  let originalFetch: typeof globalThis.fetch

  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    originalFetch = globalThis.fetch
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : (input as Request).url
      if (url.includes('/api/me')) {
        return new Response(JSON.stringify(mockMeUser), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      return new Response(null, { status: 404 })
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
  })

  it('navigates to / after successful auth for existing user', async () => {
    vi.mocked(postAuthCallback).mockResolvedValue({ is_new_user: false })
    sessionStorage.setItem('oauth_state', 'valid-state')
    sessionStorage.setItem('pkce_code_verifier', 'valid-verifier')

    renderCallback('/auth/callback?code=auth-code&state=valid-state')

    await waitFor(() => {
      expect(screen.getByText('Home Page')).toBeInTheDocument()
    })
    expect(postAuthCallback).toHaveBeenCalledWith('auth-code', 'valid-verifier')
  })

  it('navigates to / after successful auth for new user', async () => {
    vi.mocked(postAuthCallback).mockResolvedValue({ is_new_user: true })
    sessionStorage.setItem('oauth_state', 'valid-state')
    sessionStorage.setItem('pkce_code_verifier', 'valid-verifier')

    renderCallback('/auth/callback?code=auth-code&state=valid-state')

    await waitFor(() => {
      expect(screen.getByText('Home Page')).toBeInTheDocument()
    })
  })

  it('shows error message when API call fails', async () => {
    vi.mocked(postAuthCallback).mockRejectedValue(new Error('Auth callback failed'))
    sessionStorage.setItem('oauth_state', 'valid-state')
    sessionStorage.setItem('pkce_code_verifier', 'valid-verifier')

    renderCallback('/auth/callback?code=auth-code&state=valid-state')

    await waitFor(() => {
      expect(screen.getByText(/auth callback failed/i)).toBeInTheDocument()
    })
  })

  it('shows error when PKCE verifier is missing from sessionStorage', () => {
    sessionStorage.setItem('oauth_state', 'valid-state')
    // pkce_code_verifier intentionally not set

    renderCallback('/auth/callback?code=auth-code&state=valid-state')

    expect(screen.getByText(/missing pkce code verifier/i)).toBeInTheDocument()
  })

  it('clears sessionStorage keys after initiating the callback', async () => {
    vi.mocked(postAuthCallback).mockResolvedValue({ is_new_user: false })
    sessionStorage.setItem('oauth_state', 'valid-state')
    sessionStorage.setItem('pkce_code_verifier', 'valid-verifier')

    renderCallback('/auth/callback?code=auth-code&state=valid-state')

    await waitFor(() => {
      expect(sessionStorage.getItem('oauth_state')).toBeNull()
      expect(sessionStorage.getItem('pkce_code_verifier')).toBeNull()
    })
  })

  it('refetches the current user before navigating home', async () => {
    vi.mocked(postAuthCallback).mockResolvedValue({ is_new_user: false })
    sessionStorage.setItem('oauth_state', 'valid-state')
    sessionStorage.setItem('pkce_code_verifier', 'valid-verifier')

    renderCallback('/auth/callback?code=auth-code&state=valid-state')

    await waitFor(() => {
      expect(screen.getByText('Home Page')).toBeInTheDocument()
    })
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/me', { credentials: 'include' })
  })
})
