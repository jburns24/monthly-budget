import type { AssetContribution } from '@/types/asset'

/** Which dialog is open on the asset detail page, if any. */
export type AssetDialogState =
  | { kind: 'edit-asset' }
  | { kind: 'loan' }
  | { kind: 'correction' }
  | { kind: 'valuation' }
  | { kind: 'contribution'; contribution?: AssetContribution }
  | { kind: 'sell' }
  | { kind: 'delete-asset' }
  | { kind: 'unsell' }
  | { kind: 'delete-loan' }
  | { kind: 'delete-correction'; id: string }
  | { kind: 'delete-valuation'; id: string }
  | { kind: 'delete-contribution'; id: string }
