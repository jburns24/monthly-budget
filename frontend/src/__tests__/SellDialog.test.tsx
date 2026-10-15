import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect } from 'vitest'
import SellDialog from '../components/assets/SellDialog'
import system from '../theme'
import type { AssetDetail } from '../types/asset'
import { todayString } from '../utils/assets'

vi.mock('../api/assets', () => ({ sellAsset: vi.fn() }))
vi.mock('../components/ui/toaster', () => ({
  toaster: { create: vi.fn() },
  Toaster: vi.fn(() => null),
}))

const asset = {
  id: 'asset-1',
  name: 'Maple Street',
  purchase_date: '2021-06-01',
} as AssetDetail

function renderDialog() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <SellDialog familyId="fam-1" asset={asset} onClose={vi.fn()} />
      </QueryClientProvider>
    </ChakraProvider>
  )
}

async function setDate(value: string) {
  const input = await screen.findByLabelText(/^Sale date/)
  await userEvent.clear(input)
  await userEvent.type(input, value)
}

describe('SellDialog dates', () => {
  it('limits the sale date to between the purchase date and today', async () => {
    renderDialog()
    const input = await screen.findByLabelText(/^Sale date/)
    expect(input).toHaveAttribute('min', '2021-06-01')
    expect(input).toHaveAttribute('max', todayString())
  })

  it('blocks a sale date in the future or before the purchase', async () => {
    renderDialog()
    await userEvent.type(await screen.findByLabelText(/^Sale price/), '480000')
    expect(screen.getByTestId('sell-submit-btn')).toBeEnabled()

    await setDate('2999-01-01')
    expect(screen.getByTestId('sell-submit-btn')).toBeDisabled()

    await setDate('2021-05-31')
    expect(screen.getByTestId('sell-submit-btn')).toBeDisabled()

    await setDate('2021-06-01')
    expect(screen.getByTestId('sell-submit-btn')).toBeEnabled()
  })
})
