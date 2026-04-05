import { Button, Text } from '@chakra-ui/react'
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
import { deleteCategory } from '../../api/categories'
import type { Category } from '../../types/categories'
import { toaster } from '../ui/toaster'

interface ArchiveCategoryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
  category: Category | null
}

function ArchiveCategoryDialog({
  open,
  onOpenChange,
  familyId,
  category,
}: ArchiveCategoryDialogProps) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => {
      if (!category) throw new Error('No category selected')
      return deleteCategory(familyId, category.id)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['categories', familyId] })
      if (data.deleted) {
        toaster.create({
          title: 'Category deleted successfully',
          type: 'success',
          duration: 4000,
        })
      } else if (data.archived) {
        toaster.create({
          title: `Category archived (${data.expense_count} expense${data.expense_count === 1 ? '' : 's'} reference it)`,
          type: 'info',
          duration: 4000,
        })
      }
      onOpenChange(false)
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to delete category. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  const handleClose = () => {
    if (!mutation.isPending) {
      onOpenChange(false)
    }
  }

  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && handleClose()}>
      <DialogBackdrop />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete Category</DialogTitle>
        </DialogHeader>
        <DialogBody>
          {category ? (
            <Text>
              Delete <strong>{category.name}</strong>? If this category has associated expenses, it
              will be archived instead of permanently deleted.
            </Text>
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            colorPalette="red"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!category}
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </DialogRoot>
  )
}

export default ArchiveCategoryDialog
