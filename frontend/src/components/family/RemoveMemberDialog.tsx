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
import { removeMember } from '../../api/family'
import type { FamilyMember } from '../../types/family'
import { toaster } from '../ui/toaster'

interface RemoveMemberDialogProps {
  member: FamilyMember
  familyId: string
  open: boolean
  onClose: () => void
}

function RemoveMemberDialog({ member, familyId, open, onClose }: RemoveMemberDialogProps) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => removeMember(familyId, member.user_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family', familyId] })
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
      toaster.create({
        title: 'Member removed',
        description: `${member.display_name} has been removed from the family.`,
        type: 'success',
        duration: 4000,
      })
      onClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to remove member. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && onClose()}>
      <DialogBackdrop />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove Member</DialogTitle>
        </DialogHeader>
        <DialogBody>
          Remove {member.display_name} from this family? This action cannot be undone.
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button colorPalette="red" onClick={() => mutation.mutate()} loading={mutation.isPending}>
            Remove
          </Button>
        </DialogFooter>
      </DialogContent>
    </DialogRoot>
  )
}

export default RemoveMemberDialog
