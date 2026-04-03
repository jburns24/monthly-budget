import { useState } from 'react'
import { Button } from '@chakra-ui/react'
import {
  DialogRoot,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogBody,
  DialogFooter,
  DialogBackdrop,
} from '@chakra-ui/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { leaveFamily } from '../../api/family'
import { toaster } from '../ui/toaster'

interface LeaveButtonProps {
  familyId: string
  familyName: string
}

function LeaveButton({ familyId, familyName }: LeaveButtonProps) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => leaveFamily(familyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
      queryClient.invalidateQueries({ queryKey: ['family'] })
      toaster.create({
        title: 'Left family',
        description: `You have left ${familyName}.`,
        type: 'success',
        duration: 4000,
      })
      setOpen(false)
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to leave family. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  return (
    <>
      <Button variant="outline" colorPalette="red" size="sm" onClick={() => setOpen(true)} mt={6}>
        Leave Family
      </Button>
      <DialogRoot open={open} onOpenChange={(e) => !e.open && setOpen(false)}>
        <DialogBackdrop />
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Leave Family</DialogTitle>
          </DialogHeader>
          <DialogBody>
            Are you sure you want to leave {familyName}? You will need a new invite to rejoin.
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={mutation.isPending}>
              Cancel
            </Button>
            <Button
              colorPalette="red"
              onClick={() => mutation.mutate()}
              loading={mutation.isPending}
            >
              Leave
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogRoot>
    </>
  )
}

export default LeaveButton
