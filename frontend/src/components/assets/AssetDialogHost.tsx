import {
  deleteAsset,
  deleteContribution,
  deleteCorrection,
  deleteLoan,
  deleteValuation,
  unsellAsset,
} from '@/api/assets'
import type { AssetDetail } from '@/types/asset'
import AssetFormDialog from './AssetFormDialog'
import ConfirmMutationDialog from './ConfirmMutationDialog'
import ContributionDialog from './ContributionDialog'
import CorrectionDialog from './CorrectionDialog'
import LoanDialog from './LoanDialog'
import SellDialog from './SellDialog'
import ValuationDialog from './ValuationDialog'
import type { AssetDialogState } from './assetDialogState'

interface AssetDialogHostProps {
  familyId: string
  asset: AssetDetail
  dialog: AssetDialogState | null
  onClose: () => void
  onDeleted: () => void
}

/** Renders whichever dialog the detail page has open. Each mounts fresh, so forms start clean. */
function AssetDialogHost({ familyId, asset, dialog, onClose, onDeleted }: AssetDialogHostProps) {
  if (!dialog) return null
  const confirm = (props: {
    title: string
    message: string
    confirmLabel: string
    success: string
    run: () => Promise<unknown>
    onDone?: () => void
    destructive?: boolean
    deletesAssetId?: string
  }) => <ConfirmMutationDialog familyId={familyId} onClose={onClose} {...props} />

  switch (dialog.kind) {
    case 'edit-asset':
      return <AssetFormDialog familyId={familyId} asset={asset} onClose={onClose} />
    case 'loan':
      return (
        <LoanDialog familyId={familyId} assetId={asset.id} loan={asset.loan} onClose={onClose} />
      )
    case 'correction':
      return <CorrectionDialog familyId={familyId} assetId={asset.id} onClose={onClose} />
    case 'valuation':
      return <ValuationDialog familyId={familyId} assetId={asset.id} onClose={onClose} />
    case 'contribution':
      return (
        <ContributionDialog
          familyId={familyId}
          assetId={asset.id}
          contribution={dialog.contribution}
          onClose={onClose}
        />
      )
    case 'sell':
      return <SellDialog familyId={familyId} asset={asset} onClose={onClose} />
    case 'delete-asset':
      return confirm({
        title: `Delete ${asset.name}?`,
        message:
          "Expenses and recurring entries linked to it stay in your budget, but they're unlinked. This can't be undone.",
        confirmLabel: 'Delete asset',
        success: 'Asset deleted',
        run: () => deleteAsset(familyId, asset.id),
        onDone: onDeleted,
        deletesAssetId: asset.id,
      })
    case 'unsell':
      return confirm({
        title: 'Undo the sale?',
        message: 'The asset goes back to your active list and its numbers update to today.',
        confirmLabel: 'Undo sale',
        success: 'Sale undone',
        run: () => unsellAsset(familyId, asset.id),
        destructive: false,
      })
    case 'delete-loan':
      return confirm({
        title: 'Remove the loan?',
        message:
          'This also removes its balance corrections. Loan payments already in your budget stay there.',
        confirmLabel: 'Remove loan',
        success: 'Loan removed',
        run: () => deleteLoan(familyId, asset.id),
      })
    case 'delete-correction':
      return confirm({
        title: 'Delete this correction?',
        message: 'The loan balance goes back to following the payment schedule.',
        confirmLabel: 'Delete',
        success: 'Correction deleted',
        run: () => deleteCorrection(familyId, asset.id, dialog.id),
      })
    case 'delete-valuation':
      return confirm({
        title: 'Delete this value?',
        message: 'The market value goes back to the estimate for that period.',
        confirmLabel: 'Delete',
        success: 'Value deleted',
        run: () => deleteValuation(familyId, asset.id, dialog.id),
      })
    case 'delete-contribution':
      return confirm({
        title: 'Delete this past spending?',
        message: "It no longer counts toward this asset's totals.",
        confirmLabel: 'Delete',
        success: 'Past spending deleted',
        run: () => deleteContribution(familyId, asset.id, dialog.id),
      })
  }
}

export default AssetDialogHost
