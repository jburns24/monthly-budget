import { useAssetMutation } from '@/hooks/useAssets'
import ConfirmDialog from './ConfirmDialog'

interface ConfirmMutationDialogProps {
  familyId: string
  title: string
  message: string
  confirmLabel: string
  /** Toast title once it worked. */
  success: string
  run: () => Promise<unknown>
  onClose: () => void
  /** Runs after success, before the dialog closes. */
  onDone?: () => void
  destructive?: boolean
  /** Set when the write deletes this asset. */
  deletesAssetId?: string
}

/** A confirm dialog wired to an asset write. */
function ConfirmMutationDialog({
  familyId,
  title,
  message,
  confirmLabel,
  success,
  run,
  onClose,
  onDone,
  destructive,
  deletesAssetId,
}: ConfirmMutationDialogProps) {
  const mutation = useAssetMutation(familyId, run, {
    success,
    deletesAssetId,
    onSuccess: () => {
      onDone?.()
      onClose()
    },
  })
  return (
    <ConfirmDialog
      title={title}
      message={message}
      confirmLabel={confirmLabel}
      onConfirm={() => mutation.mutate()}
      onClose={onClose}
      isPending={mutation.isPending}
      destructive={destructive}
    />
  )
}

export default ConfirmMutationDialog
