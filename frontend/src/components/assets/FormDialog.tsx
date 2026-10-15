import type { ReactNode } from 'react'
import { Button, Stack } from '@chakra-ui/react'
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

interface FormDialogProps {
  title: string
  onClose: () => void
  onSubmit: () => void
  submitLabel: string
  submitTestId: string
  isValid: boolean
  isPending: boolean
  children: ReactNode
}

/**
 * Shell shared by the asset dialogs. It is mounted only while it is showing, so each opening
 * starts from fresh form state and the parent decides what is open.
 */
function FormDialog({
  title,
  onClose,
  onSubmit,
  submitLabel,
  submitTestId,
  isValid,
  isPending,
  children,
}: FormDialogProps) {
  return (
    <DialogRoot
      open
      onOpenChange={(e) => !e.open && onClose()}
      placement={{ base: 'bottom', md: 'center' }}
      scrollBehavior="inside"
    >
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <Stack gap={4}>{children}</Stack>
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" minH="44px" onClick={onClose} disabled={isPending}>
              Cancel
            </Button>
            <Button
              colorPalette="brand"
              minH="44px"
              onClick={onSubmit}
              loading={isPending}
              disabled={!isValid}
              data-testid={submitTestId}
            >
              {submitLabel}
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default FormDialog
