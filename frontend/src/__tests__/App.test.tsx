import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import App from '../App'
import system from '../theme'

// Mock useAuth so the protected route resolves without a real /api/me call
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../hooks/useAuth'

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <MemoryRouter>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

describe('App', () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: '1',
        email: 'test@example.com',
        display_name: 'Test User',
        avatar_url: null,
        timezone: 'UTC',
      },
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
  })

  it('renders Monthly Budget heading when authenticated', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <App />
      </Wrapper>
    )
    expect(screen.getByRole('heading', { name: 'Monthly Budget' })).toBeInTheDocument()
  })
})
