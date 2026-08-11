import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fetchCurrentUser } from '../hooks/useAuth'

const mockUser = {
  id: 'user-1',
  email: 'user@example.com',
  display_name: 'Test User',
  avatar_url: null,
  timezone: 'UTC',
  family: null,
}

describe('fetchCurrentUser', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    // apiClient redirects here on hard auth failure; the auth probe must not.
    vi.stubGlobal('location', { href: '' })
  })

  it('refreshes an expired access token and returns the user', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 200 }))
      .mockResolvedValueOnce(
        new Response(JSON.stringify(mockUser), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      )

    const user = await fetchCurrentUser()

    expect(user).toEqual(mockUser)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/me',
      expect.objectContaining({ credentials: 'include' })
    )
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/refresh',
      expect.objectContaining({ method: 'POST', credentials: 'include' })
    )
    expect(window.location.href).toBe('')
  })

  it('returns null when refresh fails without forcing a hard redirect', async () => {
    const fetchMock = vi.mocked(fetch)
    fetchMock
      .mockResolvedValueOnce(new Response(null, { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 401 }))

    const user = await fetchCurrentUser()

    expect(user).toBeNull()
    expect(window.location.href).toBe('')
  })
})
