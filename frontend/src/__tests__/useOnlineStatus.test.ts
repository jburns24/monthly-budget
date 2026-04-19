import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useOnlineStatus } from '@/hooks/useOnlineStatus'

describe('useOnlineStatus', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'onLine', { value: true, writable: true, configurable: true })
  })

  it('returns true when navigator.onLine is true initially', () => {
    const { result } = renderHook(() => useOnlineStatus())
    expect(result.current).toBe(true)
  })

  it('updates to false when window dispatches an offline event', () => {
    const { result } = renderHook(() => useOnlineStatus())

    act(() => {
      Object.defineProperty(navigator, 'onLine', {
        value: false,
        writable: true,
        configurable: true,
      })
      window.dispatchEvent(new Event('offline'))
    })

    expect(result.current).toBe(false)
  })

  it('updates to true when window dispatches an online event', () => {
    Object.defineProperty(navigator, 'onLine', { value: false, writable: true, configurable: true })
    const { result } = renderHook(() => useOnlineStatus())

    act(() => {
      Object.defineProperty(navigator, 'onLine', {
        value: true,
        writable: true,
        configurable: true,
      })
      window.dispatchEvent(new Event('online'))
    })

    expect(result.current).toBe(true)
  })

  it('removes event listeners on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const { unmount } = renderHook(() => useOnlineStatus())

    unmount()

    expect(removeSpy).toHaveBeenCalledWith('online', expect.any(Function))
    expect(removeSpy).toHaveBeenCalledWith('offline', expect.any(Function))

    removeSpy.mockRestore()
  })
})
