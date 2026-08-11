import { render, screen, waitFor } from '@testing-library/react'
import { ChakraProvider } from '@chakra-ui/react'
import { describe, it, expect } from 'vitest'
import SafeToSpendCard from '../components/dashboard/SafeToSpendCard'
import system from '../theme'

function renderCard(props: { totalIncomeCents: number; totalSpentCents: number }) {
  return render(
    <ChakraProvider value={system}>
      <SafeToSpendCard {...props} />
    </ChakraProvider>
  )
}

describe('SafeToSpendCard', () => {
  it('shows safe-to-spend net, income, and spent when under budget', () => {
    renderCard({ totalIncomeCents: 200000, totalSpentCents: 15200 })

    expect(screen.getByText('Safe to spend')).toBeInTheDocument()
    expect(screen.getByTestId('safe-to-spend-amount')).toHaveTextContent('$1,848')
    expect(screen.getByText('Income')).toBeInTheDocument()
    expect(screen.getByTestId('safe-to-spend-income')).toHaveTextContent('$2,000')
    expect(screen.getByText('Spent')).toBeInTheDocument()
    expect(screen.getByTestId('safe-to-spend-spent')).toHaveTextContent('$152')
  })

  it('shows over-income state with absolute overage and full rose fill', async () => {
    renderCard({ totalIncomeCents: 10000, totalSpentCents: 15000 })

    expect(screen.getByText('Over income')).toBeInTheDocument()
    expect(screen.getByTestId('safe-to-spend-amount')).toHaveTextContent('$50')
    expect(screen.queryByText('Safe to spend')).not.toBeInTheDocument()

    const fill = screen.getByTestId('safe-to-spend-fill')
    expect(fill).toHaveAttribute('stroke', '#f43f5e')
    await waitFor(() => {
      expect(fill).toHaveAttribute('stroke-dashoffset', '0')
    })
  })

  it('shows zero-income hint and empty gauge when income is 0', async () => {
    renderCard({ totalIncomeCents: 0, totalSpentCents: 5000 })

    expect(screen.getByText('Safe to spend')).toBeInTheDocument()
    expect(screen.getByTestId('safe-to-spend-amount')).toHaveTextContent('$0')
    expect(screen.getByText(/add income to see what's safe to spend/i)).toBeInTheDocument()
    expect(screen.queryByText('Income')).not.toBeInTheDocument()
    expect(screen.queryByText('Spent')).not.toBeInTheDocument()

    const fill = screen.getByTestId('safe-to-spend-fill')
    await waitFor(() => {
      expect(fill).toHaveAttribute('stroke-dashoffset', '251.3')
    })
  })

  it('sets purple fill dashoffset from spent/income pct when under budget', async () => {
    // 50% spent → offset = 251.3 * 0.5
    renderCard({ totalIncomeCents: 10000, totalSpentCents: 5000 })

    const fill = screen.getByTestId('safe-to-spend-fill')
    expect(fill).toHaveAttribute('stroke', '#a855f7')
    await waitFor(() => {
      expect(fill).toHaveAttribute('stroke-dashoffset', '125.65')
    })
  })
})
