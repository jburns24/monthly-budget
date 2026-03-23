/**
 * Frontend auth integration test.
 *
 * Exercises the complete auth redirect flow end-to-end:
 *   1. Unauthenticated user visits / → ProtectedRoute redirects to /login
 *   2. User clicks "Sign in with Google" → PKCE state written to sessionStorage
 *   3. We simulate Google's OAuth redirect to /auth/callback
 *   4. AuthCallbackPage calls postAuthCallback (mocked) → navigates to /
 *   5. ProtectedRoute re-mounts with fresh cache → /api/me returns 200 → HomePage
 */

import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { useEffect } from 'react'
import App from '../App'
import system from '../theme'

// Mock postAuthCallback so AuthCallbackPage doesn't make real API calls
vi.mock('../api/auth', () => ({
  postAuthCallback: vi.fn(),
}))

import { postAuthCallback } from '../api/auth'

// ---------------------------------------------------------------------------
// NavCapture: exposes MemoryRouter's navigate() to the test so we can drive
// route changes programmatically (simulating Google's OAuth redirect back).
// ---------------------------------------------------------------------------

let capturedNavigate: ReturnType<typeof useNavigate> | null = null

function NavCapture() {
  const nav = useNavigate()
  useEffect(() => {
    capturedNavigate = nav
  }, [nav])
  return null
}

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

const mockUser = {
  id: 'user-integration-1',
  email: 'integration@example.com',
  display_name: 'Integration User',
  avatar_url: null as string | null,
  timezone: 'America/New_York',
}

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe('Auth integration: full redirect flow', () => {
  let meCallCount: number
  let originalFetch: typeof globalThis.fetch

  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    capturedNavigate = null
    meCallCount = 0
    originalFetch = globalThis.fetch

    // Prevent LoginPage's window.location.href = GOOGLE_URL from navigating
    // away in the test environment.
    vi.stubGlobal('location', {
      href: '',
      origin: 'http://localhost',
      pathname: '/',
      search: '',
      hash: '',
      assign: vi.fn(),
      replace: vi.fn(),
      reload: vi.fn(),
    })

    // Intercept fetch calls
    globalThis.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.toString()
            : (input as Request).url

      if (url.includes('/api/me')) {
        meCallCount++
        if (meCallCount === 1) {
          // First call: user is not yet authenticated
          return new Response(null, { status: 401 })
        }
        // Subsequent calls: user authenticated after callback
        return new Response(JSON.stringify(mockUser), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      if (url.includes('/api/auth/refresh')) {
        // Refresh is not expected in this flow; return 401 so apiClient doesn't loop
        return new Response(null, { status: 401 })
      }

      if (url.includes('/api/health')) {
        return new Response(JSON.stringify({ status: 'ok' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      return new Response(null, { status: 404 })
    }) as typeof fetch
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.unstubAllGlobals()
  })

  it('unauthenticated user → /login → sign in → callback → / with user profile', async () => {
    vi.mocked(postAuthCallback).mockResolvedValue({ is_new_user: false })

    // gcTime: 0 ensures the ['currentUser'] cache entry is garbage-collected
    // when ProtectedRoute unmounts (while /login is shown), so the subsequent
    // mount after callback triggers a fresh /api/me fetch returning the user.
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          staleTime: 0,
          gcTime: 0,
        },
      },
    })

    render(
      <MemoryRouter initialEntries={['/']}>
        <ChakraProvider value={system}>
          <QueryClientProvider client={queryClient}>
            <NavCapture />
            <App />
          </QueryClientProvider>
        </ChakraProvider>
      </MemoryRouter>
    )

    // ── Step 1: Unauthenticated → ProtectedRoute redirects to /login ─────
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sign in with google/i })).toBeInTheDocument()
    })

    // ── Step 2: Click "Sign in with Google" ──────────────────────────────
    // LoginPage generates PKCE params and writes to sessionStorage before
    // setting window.location.href (which we've stubbed out above).
    fireEvent.click(screen.getByRole('button', { name: /sign in with google/i }))

    await waitFor(() => {
      expect(sessionStorage.getItem('oauth_state')).not.toBeNull()
      expect(sessionStorage.getItem('pkce_code_verifier')).not.toBeNull()
    })

    const oauthState = sessionStorage.getItem('oauth_state')!

    // ── Step 3: Simulate Google's OAuth redirect to /auth/callback ───────
    // In production, Google does a full-page redirect; here we drive the
    // MemoryRouter directly using the captured navigate function.
    expect(capturedNavigate).not.toBeNull()
    act(() => {
      capturedNavigate!(`/auth/callback?code=test-code&state=${oauthState}`)
    })

    // ── Step 4: AuthCallbackPage calls postAuthCallback ──────────────────
    await waitFor(() => {
      expect(postAuthCallback).toHaveBeenCalledWith('test-code', expect.any(String))
    })

    // ── Step 5: Successful callback → navigate to / → /api/me 200 ────────
    // With gcTime:0 the cached null was GC'd when ProtectedRoute unmounted,
    // so ProtectedRoute re-mounts with isLoading=true, fetches /api/me (now
    // returns 200), and renders HomePage.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /monthly budget/i })).toBeInTheDocument()
    })
  })
})
