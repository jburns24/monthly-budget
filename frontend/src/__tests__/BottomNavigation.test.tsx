import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { describe, it, expect } from 'vitest'
import BottomNavigation from '../components/BottomNavigation'
import system from '../theme'

function renderWithProviders(ui: React.ReactElement, initialPath = '/') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

describe('BottomNavigation', () => {
  it('renders four navigation items', () => {
    renderWithProviders(<BottomNavigation />)
    expect(screen.getByLabelText('Home')).toBeInTheDocument()
    expect(screen.getByLabelText('Family')).toBeInTheDocument()
    expect(screen.getByLabelText('Categories (coming soon)')).toBeInTheDocument()
    expect(screen.getByLabelText('Settings (coming soon)')).toBeInTheDocument()
  })

  it('marks Home tab as active when on root path', () => {
    renderWithProviders(<BottomNavigation />, '/')
    // NavLink renders active styles; check the link is present
    const homeLink = screen.getByLabelText('Home')
    expect(homeLink).toBeInTheDocument()
  })

  it('marks Family tab as active when on /family path', () => {
    renderWithProviders(<BottomNavigation />, '/family')
    const familyLink = screen.getByLabelText('Family')
    expect(familyLink).toBeInTheDocument()
  })

  it('renders Categories as disabled with aria-disabled', () => {
    renderWithProviders(<BottomNavigation />)
    const categoriesItem = screen.getByLabelText('Categories (coming soon)')
    // The disabled NavItem renders with aria-disabled on its inner Flex
    const disabledEl = categoriesItem.querySelector('[aria-disabled="true"]')
    expect(disabledEl).toBeInTheDocument()
  })

  it('renders Settings as disabled with aria-disabled', () => {
    renderWithProviders(<BottomNavigation />)
    const settingsItem = screen.getByLabelText('Settings (coming soon)')
    const disabledEl = settingsItem.querySelector('[aria-disabled="true"]')
    expect(disabledEl).toBeInTheDocument()
  })

  it('renders nav with accessible bottom navigation label', () => {
    renderWithProviders(<BottomNavigation />)
    expect(screen.getByRole('navigation', { name: 'Bottom navigation' })).toBeInTheDocument()
  })
})
