import { apiClient } from './client'
import type { AuthCallbackResponse, MeResponse, UserUpdate } from '../types/api'

export async function postAuthCallback(
  code: string,
  codeVerifier: string
): Promise<AuthCallbackResponse> {
  const response = await apiClient('/api/auth/callback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code, code_verifier: codeVerifier }),
  })
  if (!response.ok) {
    throw new Error('Auth callback failed')
  }
  return response.json() as Promise<AuthCallbackResponse>
}

export async function postAuthRefresh(): Promise<void> {
  const response = await apiClient('/api/auth/refresh', {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error('Token refresh failed')
  }
}

export async function postAuthLogout(): Promise<void> {
  const response = await apiClient('/api/auth/logout', {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error('Logout failed')
  }
}

export async function getMe(): Promise<MeResponse> {
  const response = await apiClient('/api/me')
  if (!response.ok) {
    throw new Error('Failed to fetch user')
  }
  return response.json() as Promise<MeResponse>
}

export async function putMe(data: UserUpdate): Promise<MeResponse> {
  const response = await apiClient('/api/me', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to update user')
  }
  return response.json() as Promise<MeResponse>
}
