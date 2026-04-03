import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import CreateFamilyView from '../components/family/CreateFamilyView'
import system from '../theme'

// Mock the family API module
vi.mock('../api/family', () => ({
  createFamily: vi.fn(),
}))

import { createFamily } from '../api/family'

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </ChakraProvider>
  )
}

describe('CreateFamilyView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the heading and form fields', () => {
    renderWithProviders(<CreateFamilyView />)

    expect(screen.getByRole('heading', { name: /create your family/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/the smiths/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /create family/i })).toBeInTheDocument()
  })

  it('disables submit button when name is empty', () => {
    renderWithProviders(<CreateFamilyView />)

    const button = screen.getByRole('button', { name: /create family/i })
    expect(button).toBeDisabled()
  })

  it('enables submit button when name has value', () => {
    renderWithProviders(<CreateFamilyView />)

    const input = screen.getByPlaceholderText(/the smiths/i)
    fireEvent.change(input, { target: { value: 'The Smiths' } })

    const button = screen.getByRole('button', { name: /create family/i })
    expect(button).not.toBeDisabled()
  })

  it('calls createFamily API when form is submitted with a valid name', async () => {
    vi.mocked(createFamily).mockResolvedValue({
      id: 'fam-123',
      name: 'The Smiths',
      timezone: 'America/New_York',
      created_by: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
      members: [],
    })

    renderWithProviders(<CreateFamilyView />)

    const input = screen.getByPlaceholderText(/the smiths/i)
    fireEvent.change(input, { target: { value: 'The Smiths' } })

    const form = input.closest('form')!
    fireEvent.submit(form)

    await waitFor(() => {
      expect(createFamily).toHaveBeenCalledWith('The Smiths', 'America/New_York')
    })
  })

  it('does not call createFamily when name is blank', () => {
    renderWithProviders(<CreateFamilyView />)

    const input = screen.getByPlaceholderText(/the smiths/i)
    const form = input.closest('form')!
    fireEvent.submit(form)

    expect(createFamily).not.toHaveBeenCalled()
  })

  it('trims whitespace from the family name before submitting', async () => {
    vi.mocked(createFamily).mockResolvedValue({
      id: 'fam-123',
      name: 'The Smiths',
      timezone: 'America/New_York',
      created_by: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
      members: [],
    })

    renderWithProviders(<CreateFamilyView />)

    const input = screen.getByPlaceholderText(/the smiths/i)
    fireEvent.change(input, { target: { value: '  The Smiths  ' } })

    const form = input.closest('form')!
    fireEvent.submit(form)

    await waitFor(() => {
      expect(createFamily).toHaveBeenCalledWith('The Smiths', 'America/New_York')
    })
  })
})
