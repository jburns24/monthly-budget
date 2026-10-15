import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('../api/client', () => ({ apiClient: vi.fn() }))

import { apiClient } from '../api/client'
import { addValuation, deleteAsset, deleteCorrection, updateAsset } from '../api/assets'

function reply(status: number, body?: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), { status })
}

describe('assets api client', () => {
  beforeEach(() => vi.clearAllMocks())

  it('resolves a 204 delete without reading a body', async () => {
    vi.mocked(apiClient).mockResolvedValue(reply(204))
    await expect(deleteAsset('f1', 'a1')).resolves.toBeUndefined()
    await expect(deleteCorrection('f1', 'a1', 'c1')).resolves.toBeUndefined()
    expect(apiClient).toHaveBeenCalledWith('/api/families/f1/assets/a1', { method: 'DELETE' })
  })

  it('returns the created row from a 201', async () => {
    vi.mocked(apiClient).mockResolvedValue(reply(201, { id: 'v1', value_cents: 100 }))
    await expect(
      addValuation('f1', 'a1', { as_of_date: '2026-01-01', value_cents: 100 })
    ).resolves.toEqual({ id: 'v1', value_cents: 100 })
  })

  it('surfaces a plain-text server error and falls back otherwise', async () => {
    vi.mocked(apiClient).mockResolvedValueOnce(reply(400, { detail: 'No fields to update' }))
    await expect(updateAsset('f1', 'a1', {})).rejects.toThrow('No fields to update')
    vi.mocked(apiClient).mockResolvedValueOnce(reply(422, { detail: [{ msg: 'x' }] }))
    await expect(updateAsset('f1', 'a1', {})).rejects.toThrow('Failed to update asset')
  })
})
