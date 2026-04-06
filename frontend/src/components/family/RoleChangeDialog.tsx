import { Button } from '@chakra-ui/react'
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
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { changeRole } from '../../api/family'
import type { FamilyMember } from '../../types/family'
import { toaster } from '../ui/toaster'

interface RoleChangeDialogProps {
  member: FamilyMember
  familyId: string
  open: boolean
  onClose: () => void
}

function RoleChangeDialog({ member, familyId, open, onClose }: RoleChangeDialogProps) {
  const queryClient = useQueryClient()
  const newRole = member.role === 'admin' ? 'member' : 'admin'

  const mutation = useMutation({
    mutationFn: () => changeRole(familyId, member.user_id, newRole),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['family', familyId] })
      toaster.create({
        title: 'Role updated',
        description: `${member.display_name} is now ${newRole === 'admin' ? 'an admin' : 'a member'}.`,
        type: 'success',
        duration: 4000,
      })
      onClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to change role. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && onClose()} placement="center">
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Change Role</DialogTitle>
          </DialogHeader>
          <DialogBody>
            Change {member.display_name}&apos;s role to {newRole === 'admin' ? 'Admin' : 'Member'}?
          </DialogBody>
          <DialogFooter>
            <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
              Cancel
            </Button>
            <Button
              colorPalette="brand"
              onClick={() => mutation.mutate()}
              loading={mutation.isPending}
            >
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default RoleChangeDialog
