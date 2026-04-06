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
import { createCategory } from '../../api/categories'
import { toaster } from '../ui/toaster'

interface CreateCategoryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
}

function CreateCategoryDialog({ open, onOpenChange, familyId }: CreateCategoryDialogProps) {
  const queryClient = useQueryClient()
  const [name, setName] = useState('')
  const [icon, setIcon] = useState('')
  const [sortOrder, setSortOrder] = useState<string>('0')

  const mutation = useMutation({
    mutationFn: () =>
      createCategory(familyId, {
        name: name.trim(),
        icon: icon.trim() || null,
        sort_order: parseInt(sortOrder, 10) || 0,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['categories', familyId] })
      toaster.create({
        title: 'Category created',
        description: `"${name.trim()}" has been added.`,
        type: 'success',
        duration: 4000,
      })
      handleClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to create category. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  function handleClose() {
    setName('')
    setIcon('')
    setSortOrder('0')
    onOpenChange(false)
  }

  const isValid = name.trim().length > 0 && name.trim().length <= 100

  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && handleClose()} placement="center">
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Category</DialogTitle>
          </DialogHeader>
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
            <Button variant="ghost" onClick={handleClose} disabled={mutation.isPending}>
              Cancel
            </Button>
            <Button
              colorPalette="brand"
              onClick={() => mutation.mutate()}
              loading={mutation.isPending}
              disabled={!isValid}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default CreateCategoryDialog
