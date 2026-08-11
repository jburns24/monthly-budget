interface QueueEntry {
  resolve: (response: Response) => void
  reject: (reason: unknown) => void
  input: string
  init: RequestInit | undefined
}

export interface ApiClientOptions {
  /**
   * When true (default), a failed refresh sends the browser to /login.
   * Auth probes (e.g. fetchCurrentUser on /login) should set false so a
   * missing session returns null instead of forcing a navigation loop.
   */
  redirectOnAuthFailure?: boolean
}

let isRefreshing = false
let requestQueue: QueueEntry[] = []

function processQueue(error: Error | null): void {
  const queue = requestQueue
  requestQueue = []
  queue.forEach(({ resolve, reject, input, init }) => {
    if (error !== null) {
      reject(error)
      return
    }
    fetch(input, { ...init, credentials: 'include' })
      .then((res) => resolve(res))
      .catch((err: unknown) => reject(err))
  })
}

export async function apiClient(
  input: string,
  init?: RequestInit,
  options?: ApiClientOptions
): Promise<Response> {
  const redirectOnAuthFailure = options?.redirectOnAuthFailure !== false
  const response = await fetch(input, { ...init, credentials: 'include' })

  if (response.status !== 401) {
    return response
  }

  if (isRefreshing) {
    return new Promise<Response>((resolve, reject) => {
      requestQueue.push({ resolve, reject, input, init })
    })
  }

  isRefreshing = true

  try {
    const refreshResponse = await fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    })
    if (!refreshResponse.ok) {
      throw new Error('Token refresh failed')
    }
    isRefreshing = false
    processQueue(null)
    return fetch(input, { ...init, credentials: 'include' })
  } catch (err) {
    const error = err instanceof Error ? err : new Error(String(err))
    isRefreshing = false
    processQueue(error)
    if (redirectOnAuthFailure) {
      window.location.href = '/login'
    }
    throw error
  }
}
