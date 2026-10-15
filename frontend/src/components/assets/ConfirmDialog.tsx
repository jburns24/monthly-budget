import { Button, Text } from '@chakra-ui/react'
import {
  DialogRoot,
  DialogPositioner,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogBody,
  DialogFooter,
  DialogBackdrop,
} from '@chakra-ui/react'

interface ConfirmDialogProps {
  title: string
  message: string
  confirmLabel: string
  onConfirm: () => void
  onClose: () => void
  isPending: boolean
  /** Red for something that can't be undone. */
  destructive?: boolean
}

/** Ask before a delete or a sale undo. Mounted only while showing. */
function ConfirmDialog({
  title,
  message,
  confirmLabel,
  onConfirm,
  onClose,
  isPending,
  destructive = true,
}: ConfirmDialogProps) {
  return (
    <DialogRoot
      open
      onOpenChange={(e) => !e.open && onClose()}
      placement={{ base: 'bottom', md: 'center' }}
      role="alertdialog"
    >
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Text fontSize="sm" color="ink.muted">
              {message}
            </Text>
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" minH="44px" onClick={onClose} disabled={isPending}>
              Keep
            </Button>
            <Button
              colorPalette={destructive ? 'red' : 'brand'}
              minH="44px"
              onClick={onConfirm}
              loading={isPending}
              data-testid="confirm-dialog-confirm"
            >
              {confirmLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default ConfirmDialog
