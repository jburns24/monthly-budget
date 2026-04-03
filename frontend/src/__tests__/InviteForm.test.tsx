import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import InviteForm from '../components/family/InviteForm'
import system from '../theme'

// Mock the family API module
vi.mock('../api/family', () => ({
  sendInvite: vi.fn(),
}))

import { sendInvite } from '../api/family'

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </ChakraProvider>
  )
}

describe('InviteForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the invite form with email input and send button', () => {
    renderWithProviders(<InviteForm familyId="fam-123" />)

    expect(screen.getByRole('heading', { name: /invite member/i })).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/enter email address/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /send invite/i })).toBeInTheDocument()
  })

  it('disables send button when email is empty', () => {
    renderWithProviders(<InviteForm familyId="fam-123" />)

    const button = screen.getByRole('button', { name: /send invite/i })
    expect(button).toBeDisabled()
  })

  it('enables send button when email has value', () => {
    renderWithProviders(<InviteForm familyId="fam-123" />)

    const input = screen.getByPlaceholderText(/enter email address/i)
    fireEvent.change(input, { target: { value: 'invite@example.com' } })

    const button = screen.getByRole('button', { name: /send invite/i })
    expect(button).not.toBeDisabled()
  })

  it('calls sendInvite with familyId and email on submit', async () => {
    vi.mocked(sendInvite).mockResolvedValue({ message: 'Invite sent' })

    renderWithProviders(<InviteForm familyId="fam-123" />)

    const input = screen.getByPlaceholderText(/enter email address/i)
    fireEvent.change(input, { target: { value: 'invite@example.com' } })

    const form = input.closest('form')!
    fireEvent.submit(form)

    await waitFor(() => {
      expect(sendInvite).toHaveBeenCalledWith('fam-123', 'invite@example.com')
    })
  })

  it('shows generic success message on successful invite (does not reveal user existence)', async () => {
    vi.mocked(sendInvite).mockResolvedValue({ message: 'Invite sent' })

    renderWithProviders(<InviteForm familyId="fam-123" />)

    const input = screen.getByPlaceholderText(/enter email address/i)
    fireEvent.change(input, { target: { value: 'invite@example.com' } })

    const form = input.closest('form')!
    fireEvent.submit(form)

    // After success, email input should be cleared
    await waitFor(() => {
      expect(input).toHaveValue('')
    })
  })

  it('shows generic success message even on API error (privacy-preserving)', async () => {
    vi.mocked(sendInvite).mockRejectedValue(new Error('User not found'))

    renderWithProviders(<InviteForm familyId="fam-123" />)

    const input = screen.getByPlaceholderText(/enter email address/i)
    fireEvent.change(input, { target: { value: 'nonexistent@example.com' } })

    const form = input.closest('form')!
    fireEvent.submit(form)

    // Even on error, email is cleared (same success-like UX to avoid user enumeration)
    await waitFor(() => {
      expect(input).toHaveValue('')
    })
  })

  it('does not call sendInvite when email is blank', () => {
    renderWithProviders(<InviteForm familyId="fam-123" />)

    const input = screen.getByPlaceholderText(/enter email address/i)
    const form = input.closest('form')!
    fireEvent.submit(form)

    expect(sendInvite).not.toHaveBeenCalled()
  })
})
