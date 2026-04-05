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
import { deleteExpense } from '../../api/expenses'
import type { Expense } from '../../types/expenses'
import { toaster } from '../ui/toaster'

interface DeleteExpenseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
  expense: Expense | null
}

function formatAmount(amountCents: number): string {
  return `$${(amountCents / 100).toFixed(2)}`
}

function DeleteExpenseDialog({ open, onOpenChange, familyId, expense }: DeleteExpenseDialogProps) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => {
      if (!expense) throw new Error('No expense selected')
      return deleteExpense(familyId, expense.id)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      toaster.create({
        title: 'Expense deleted',
        type: 'success',
        duration: 4000,
      })
      onOpenChange(false)
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to delete expense. Please try again.',
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
          <DialogTitle>Delete Expense</DialogTitle>
        </DialogHeader>
        <DialogBody>
          {expense ? (
            <Text>
              Delete <strong>{expense.description || '(no description)'}</strong> (
              {formatAmount(expense.amount_cents)})? This action cannot be undone.
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
            disabled={!expense}
            data-testid="delete-expense-confirm"
          >
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </DialogRoot>
  )
}

export default DeleteExpenseDialog
