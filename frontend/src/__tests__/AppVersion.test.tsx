import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import system from '../theme'

vi.mock('../api/version', () => ({
  WEB_VERSION: '0.11.0',
  getApiVersion: vi.fn(),
}))

import { getApiVersion } from '../api/version'
import AppVersion from '../components/AppVersion'
import { formatVersion } from '../utils/format'

function renderVersion() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <ChakraProvider value={system}>
      <QueryClientProvider client={queryClient}>
        <AppVersion />
      </QueryClientProvider>
    </ChakraProvider>
  )
}

describe('AppVersion', () => {
  beforeEach(() => {
    vi.mocked(getApiVersion).mockReset()
  })

  it('shows the web and api versions', async () => {
    vi.mocked(getApiVersion).mockResolvedValue({ version: '0.12.0' })
    renderVersion()

    expect(await screen.findByText('web v0.11.0 · api v0.12.0')).toBeInTheDocument()
  })

  it('shows "api ?" when the version request fails', async () => {
    vi.mocked(getApiVersion).mockRejectedValue(new Error('boom'))
    renderVersion()

    expect(await screen.findByText('web v0.11.0 · api ?')).toBeInTheDocument()
  })

  it('shows a placeholder while the api version loads', () => {
    vi.mocked(getApiVersion).mockReturnValue(new Promise(() => {}))
    renderVersion()

    expect(screen.getByTestId('app-version')).toHaveTextContent('web v0.11.0 · api …')
  })
})

describe('formatVersion', () => {
  it('prefixes release versions with v and leaves others alone', () => {
    expect(formatVersion('1.2.3')).toBe('v1.2.3')
    expect(formatVersion('dev')).toBe('dev')
  })
})
