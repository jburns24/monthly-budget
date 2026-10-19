import { apiClient } from './client'
import type { VersionInfo } from '../types/version'

/** Frontend release version baked in at build time; `dev` for local builds. */
export const WEB_VERSION: string = import.meta.env.VITE_APP_VERSION || 'dev'

export async function getApiVersion(): Promise<VersionInfo> {
  const response = await apiClient('/api/version', undefined, { redirectOnAuthFailure: false })
  if (!response.ok) {
    throw new Error('Failed to fetch API version')
  }
  return response.json() as Promise<VersionInfo>
}
