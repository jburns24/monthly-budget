import type { AssetRole } from '@/types/asset'

/** The asset an expense or recurring entry is linked to, and how it counts toward it. */
export interface AssetLink {
  /** Empty when not linked. */
  assetId: string
  role: AssetRole
}

export const NO_ASSET_LINK: AssetLink = { assetId: '', role: 'maintenance' }

export function linkFromEntry(entry: {
  asset_id?: string | null
  asset_role?: AssetRole | null
}): AssetLink {
  return entry.asset_id
    ? { assetId: entry.asset_id, role: entry.asset_role ?? 'maintenance' }
    : NO_ASSET_LINK
}

/** Link fields for a create request; nothing is sent when unlinked, and income can't be linked. */
export function assetLinkFields(link: AssetLink, isIncome: boolean) {
  return link.assetId && !isIncome ? { asset_id: link.assetId, asset_role: link.role } : {}
}

/**
 * Link fields for an update request: only what changed, with explicit nulls to unlink.
 * Turning an entry into income unlinks it.
 */
export function assetLinkChanges(
  original: { asset_id?: string | null; asset_role?: AssetRole | null },
  link: AssetLink,
  isIncome: boolean
) {
  const assetId = isIncome ? '' : link.assetId
  if (!assetId) return original.asset_id ? { asset_id: null, asset_role: null } : {}
  const unchanged = assetId === original.asset_id && link.role === original.asset_role
  return unchanged ? {} : { asset_id: assetId, asset_role: link.role }
}
