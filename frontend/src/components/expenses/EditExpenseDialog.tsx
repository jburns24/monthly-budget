import { useState } from 'react'
import { Box, Button, Input, Stack, Text } from '@chakra-ui/react'
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
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { updateExpense } from '../../api/expenses'
import { getCategories } from '../../api/categories'
import type { Expense } from '../../types/expenses'
import { toaster } from '../ui/toaster'

interface EditExpenseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
  expense: Expense | null
}

interface EditFormProps {
  expense: Expense
  familyId: string
  onOpenChange: (open: boolean) => void
}

function EditForm({ expense, familyId, onOpenChange }: EditFormProps) {
  const queryClient = useQueryClient()
  const [amountStr, setAmountStr] = useState(String(expense.amount_cents / 100))
  const [description, setDescription] = useState(expense.description)
  const [categoryId, setCategoryId] = useState(expense.category.id)
  const [expenseDate, setExpenseDate] = useState(expense.expense_date)

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId),
  })

  const mutation = useMutation({
    mutationFn: () => {
      const amountCents = Math.round(parseFloat(amountStr) * 100)
      return updateExpense(familyId, expense.id, {
        amount_cents: amountCents,
        description: description.trim(),
        category_id: categoryId,
        expense_date: expenseDate,
        expected_updated_at: expense.updated_at,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      toaster.create({
        title: 'Expense updated',
        type: 'success',
        duration: 4000,
      })
      onOpenChange(false)
    },
    onError: (error: Error) => {
      if (error.message === 'CONFLICT') {
        toaster.create({
          title: 'This expense was modified by someone else. Please refresh and try again.',
          type: 'error',
          duration: 6000,
        })
      } else {
        toaster.create({
          title: 'Error',
          description: 'Failed to update expense. Please try again.',
          type: 'error',
          duration: 4000,
        })
      }
    },
  })

  const amountCents = Math.round(parseFloat(amountStr) * 100)
  const isValid =
    amountStr.trim().length > 0 &&
    !isNaN(amountCents) &&
    amountCents > 0 &&
    categoryId.trim().length > 0 &&
    expenseDate.trim().length > 0

  return (
    <>
      <DialogBody>
        <Stack gap={4}>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Amount{' '}
              <Text as="span" color="red.500">
                *
              </Text>
            </Text>
            <Input
              placeholder="e.g. 45.23"
              inputMode="decimal"
              value={amountStr}
              onChange={(e) => setAmountStr(e.target.value)}
              disabled={mutation.isPending}
              data-testid="edit-expense-amount"
            />
          </Stack>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Description
            </Text>
            <Input
              placeholder="e.g. Weekly shop"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              disabled={mutation.isPending}
              data-testid="edit-expense-description"
            />
          </Stack>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Category{' '}
              <Text as="span" color="red.500">
                *
              </Text>
            </Text>
            <Box
              as="select"
              w="full"
              h="40px"
              px={3}
              borderWidth="1px"
              borderRadius="md"
              borderColor="gray.200"
              bg="white"
              value={categoryId}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setCategoryId(e.target.value)}
              disabled={mutation.isPending}
              data-testid="edit-expense-category"
            >
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.icon ? `${cat.icon} ` : ''}
                  {cat.name}
                </option>
              ))}
            </Box>
          </Stack>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Date{' '}
              <Text as="span" color="red.500">
                *
              </Text>
            </Text>
            <Input
              type="date"
              value={expenseDate}
              onChange={(e) => setExpenseDate(e.target.value)}
              disabled={mutation.isPending}
              data-testid="edit-expense-date"
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

function EditExpenseDialog({ open, onOpenChange, familyId, expense }: EditExpenseDialogProps) {
  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && onOpenChange(false)} placement="center">
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Expense</DialogTitle>
          </DialogHeader>
          {expense && (
            <EditForm
              key={expense.id + expense.updated_at}
              expense={expense}
              familyId={familyId}
              onOpenChange={onOpenChange}
            />
          )}
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default EditExpenseDialog
