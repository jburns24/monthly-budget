import { vi, describe, it, expect, afterEach } from 'vitest'
import { getApiVersion, WEB_VERSION } from '../api/version'

describe('version api', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads /api/version', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ version: '0.12.0' }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(getApiVersion()).resolves.toEqual({ version: '0.12.0' })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/version')
  })

  it('throws on a non-ok response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 500 })))

    await expect(getApiVersion()).rejects.toThrow('Failed to fetch API version')
  })

  it('falls back to dev when no build-time version is set', () => {
    expect(WEB_VERSION).toBe('dev')
  })
})
