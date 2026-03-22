import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import App from '../App'
import system from '../theme'

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
  it('renders Monthly Budget heading', () => {
    const Wrapper = createWrapper()
    render(
      <Wrapper>
        <App />
      </Wrapper>
    )
    expect(screen.getByText('Monthly Budget')).toBeInTheDocument()
  })
})
