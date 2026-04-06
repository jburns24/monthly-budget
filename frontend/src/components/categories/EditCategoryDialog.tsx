import { useState } from 'react'
import { Button, Input, Stack, Text } from '@chakra-ui/react'
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
import { updateCategory } from '../../api/categories'
import type { Category } from '../../types/categories'
import { toaster } from '../ui/toaster'

interface EditCategoryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
  category: Category | null
}

interface EditFormProps {
  category: Category
  familyId: string
  onOpenChange: (open: boolean) => void
}

function EditForm({ category, familyId, onOpenChange }: EditFormProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState(category.name)
  const [icon, setIcon] = useState(category.icon ?? '')
  const [sortOrder, setSortOrder] = useState(String(category.sort_order))

  const mutation = useMutation({
    mutationFn: () =>
      updateCategory(familyId, category.id, {
        name: name.trim(),
        icon: icon.trim() || null,
        sort_order: parseInt(sortOrder, 10) || 0,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories', familyId] })
      toaster.create({
        title: 'Category updated',
        description: `"${name.trim()}" has been saved.`,
        type: 'success',
        duration: 4000,
      })
      onOpenChange(false)
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to update category. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  const isValid = name.trim().length > 0 && name.trim().length <= 100

  return (
    <>
      <DialogBody>
        <Stack gap={4}>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Name{' '}
              <Text as="span" color="red.500">
                *
              </Text>
            </Text>
            <Input
              placeholder="e.g. Groceries"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              disabled={mutation.isPending}
            />
          </Stack>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Icon (emoji)
            </Text>
            <Input
              placeholder="e.g. 🛒"
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              disabled={mutation.isPending}
            />
          </Stack>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Sort Order
            </Text>
            <Input
              type="number"
              placeholder="0"
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value)}
              disabled={mutation.isPending}
            />
          </Stack>
        </Stack>
      </DialogBody>
      <DialogFooter>
        <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button
          colorPalette="brand"
          onClick={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!isValid}
        >
          Save
        </Button>
      </DialogFooter>
    </>
  )
}

function EditCategoryDialog({ open, onOpenChange, familyId, category }: EditCategoryDialogProps) {
  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && onOpenChange(false)} placement="center">
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Category</DialogTitle>
          </DialogHeader>
          {category && (
            <EditForm
              key={category.id}
              category={category}
              familyId={familyId}
              onOpenChange={onOpenChange}
            />
          )}
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default EditCategoryDialog
