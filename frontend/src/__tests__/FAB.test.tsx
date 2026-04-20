import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import FAB from '../components/expenses/FAB'
import system from '../theme'

vi.mock('../hooks/useOnlineStatus', () => ({
  useOnlineStatus: vi.fn(() => true),
}))

vi.mock('../components/expenses/CreateExpenseDialog', () => ({
  default: vi.fn(({ open }: { open: boolean }) =>
    open ? <div role="dialog" data-testid="create-expense-dialog" /> : null
  ),
}))

vi.mock('../components/expenses/ReceiptCaptureDialog', () => ({
  default: vi.fn(({ open }: { open: boolean }) =>
    open ? <div role="dialog" data-testid="receipt-capture-dialog" /> : null
  ),
}))

import { useOnlineStatus } from '../hooks/useOnlineStatus'

const FAMILY_ID = 'fam-123'

function renderFAB() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <FAB familyId={FAMILY_ID} />
      </QueryClientProvider>
    </ChakraProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(useOnlineStatus).mockReturnValue(true)
})

describe('FAB — Scan Receipt button', () => {
  it('renders the scan receipt button', () => {
    renderFAB()
    expect(screen.getByTestId('fab-scan-receipt')).toBeInTheDocument()
  })

  it('scan receipt button is enabled when online', () => {
    vi.mocked(useOnlineStatus).mockReturnValue(true)
    renderFAB()
    expect(screen.getByTestId('fab-scan-receipt')).not.toBeDisabled()
  })

  it('scan receipt button is disabled when offline', () => {
    vi.mocked(useOnlineStatus).mockReturnValue(false)
    renderFAB()
    expect(screen.getByTestId('fab-scan-receipt')).toBeDisabled()
  })

  it('clicking scan receipt when online opens ReceiptCaptureDialog', async () => {
    const user = userEvent.setup()
    vi.mocked(useOnlineStatus).mockReturnValue(true)
    renderFAB()

    await user.click(screen.getByTestId('fab-scan-receipt'))

    await waitFor(() => {
      expect(screen.getByTestId('receipt-capture-dialog')).toBeInTheDocument()
    })
  })

  it('scan receipt button has aria-label', () => {
    renderFAB()
    expect(screen.getByTestId('fab-scan-receipt')).toHaveAttribute('aria-label', 'Scan receipt')
  })
})

describe('FAB — Add Expense button', () => {
  it('renders the add expense FAB', () => {
    renderFAB()
    expect(screen.getByTestId('fab-add-expense')).toBeInTheDocument()
  })

  it('clicking add expense FAB opens CreateExpenseDialog', async () => {
    const user = userEvent.setup()
    renderFAB()

    await user.click(screen.getByTestId('fab-add-expense'))

    await waitFor(() => {
      expect(screen.getByTestId('create-expense-dialog')).toBeInTheDocument()
    })
  })
})
