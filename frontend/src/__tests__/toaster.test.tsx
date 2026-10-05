import { render, screen, waitFor } from '@testing-library/react'
import { ChakraProvider } from '@chakra-ui/react'
import { describe, it, expect } from 'vitest'
import { Toaster, toaster } from '../components/ui/toaster'
import system from '../theme'

describe('Toaster', () => {
  it('shows notifications at the top so they never cover the bottom nav', async () => {
    render(
      <ChakraProvider value={system}>
        <Toaster />
      </ChakraProvider>
    )

    toaster.create({ title: 'Expense added', type: 'success', duration: 60_000 })

    await waitFor(() => expect(screen.getByText('Expense added')).toBeInTheDocument())
    const toast = screen.getByText('Expense added').closest('[data-part="root"]')
    expect(toast?.getAttribute('data-placement')).toMatch(/^top/)
  })
})
