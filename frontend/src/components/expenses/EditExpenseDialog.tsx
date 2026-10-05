import { useState } from 'react'
import { Button, Input, NativeSelectField, NativeSelectRoot, Stack, Text } from '@chakra-ui/react'
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
import { deleteExpense, updateExpense } from '../../api/expenses'
import { createRecurringExpense } from '../../api/recurring'
import { getCategories } from '../../api/categories'
import type { EntryType, Expense, ExpenseUpdate } from '../../types/expenses'
import { toaster } from '../ui/toaster'
import type { Frequency } from '../../types/recurring'
import { nextOccurrence } from '../../utils/recurrence'
import EntryTypeToggle from './EntryTypeToggle'
import RepeatFields from './RepeatFields'

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
  const [entryType, setEntryType] = useState<EntryType>(expense.entry_type)
  const [amountStr, setAmountStr] = useState(String(expense.amount_cents / 100))
  const [description, setDescription] = useState(expense.description)
  const [categoryId, setCategoryId] = useState(expense.category?.id ?? '')
  const [expenseDate, setExpenseDate] = useState(expense.expense_date)
  const [repeat, setRepeat] = useState(false)
  const [frequency, setFrequency] = useState<Frequency>('monthly')
  const [endDate, setEndDate] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const isIncome = entryType === 'income'
  const isRecurring = expense.recurring_expense_id != null

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId),
  })

  const mutation = useMutation({
    mutationFn: async () => {
      const amountCents = Math.round(parseFloat(amountStr) * 100)
      const payload: ExpenseUpdate = {
        amount_cents: amountCents,
        description: description.trim(),
        expense_date: expenseDate,
        entry_type: entryType,
        expected_updated_at: expense.updated_at,
      }
      if (!isIncome) {
        payload.category_id = categoryId
      }
      const updated = await updateExpense(familyId, expense.id, payload)
      if (repeat && !isRecurring) {
        // This entry is the first occurrence; the rule starts at the next one.
        await createRecurringExpense(familyId, {
          amount_cents: amountCents,
          description: description.trim() || undefined,
          entry_type: entryType,
          frequency,
          start_date: nextOccurrence(expenseDate, frequency),
          end_date: endDate || null,
          ...(isIncome ? {} : { category_id: categoryId }),
        })
      }
      return updated
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      if (repeat) queryClient.invalidateQueries({ queryKey: ['recurring', familyId] })
      toaster.create({
        title: repeat
          ? isIncome
            ? 'Income updated and set to repeat'
            : 'Expense updated and set to repeat'
          : isIncome
            ? 'Income updated'
            : 'Expense updated',
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
          description: isIncome
            ? 'Failed to update income. Please try again.'
            : 'Failed to update expense. Please try again.',
          type: 'error',
          duration: 4000,
        })
      }
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteExpense(familyId, expense.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      toaster.create({
        title: isIncome ? 'Income deleted' : 'Expense deleted',
        type: 'success',
        duration: 4000,
      })
      onOpenChange(false)
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to delete. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })
  const busy = mutation.isPending || deleteMutation.isPending

  const amountCents = Math.round(parseFloat(amountStr) * 100)
  const isValid =
    amountStr.trim().length > 0 &&
    !isNaN(amountCents) &&
    amountCents > 0 &&
    expenseDate.trim().length > 0 &&
    (!repeat || !endDate || endDate >= nextOccurrence(expenseDate, frequency)) &&
    (isIncome || categoryId.trim().length > 0)

  return (
    <>
      <DialogHeader>
        <DialogTitle>{isIncome ? 'Edit Income' : 'Edit Expense'}</DialogTitle>
      </DialogHeader>
      <DialogBody>
        <Stack gap={4}>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Type
            </Text>
            <EntryTypeToggle
              value={entryType}
              onChange={setEntryType}
              disabled={mutation.isPending}
            />
          </Stack>
          <RepeatFields
            repeat={repeat}
            onRepeatChange={setRepeat}
            frequency={frequency}
            onFrequencyChange={setFrequency}
            endDate={endDate}
            onEndDateChange={setEndDate}
            minEndDate={nextOccurrence(expenseDate, frequency)}
            disabled={busy}
            locked={isRecurring}
            lockedHint="Part of a recurring entry. Manage it on the Recurring page."
          />
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
              placeholder={isIncome ? 'e.g. Paycheck' : 'e.g. Weekly shop'}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              disabled={mutation.isPending}
              data-testid="edit-expense-description"
            />
          </Stack>
          {!isIncome && (
            <Stack gap={1}>
              <Text fontWeight="medium" fontSize="sm">
                Category{' '}
                <Text as="span" color="red.500">
                  *
                </Text>
              </Text>
              <NativeSelectRoot disabled={mutation.isPending}>
                <NativeSelectField
                  value={categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  data-testid="edit-expense-category"
                >
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.icon ? `${cat.icon} ` : ''}
                      {cat.name}
                    </option>
                  ))}
                </NativeSelectField>
              </NativeSelectRoot>
            </Stack>
          )}
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
      {confirmingDelete ? (
        <DialogFooter flexWrap="wrap">
          <Text mr="auto" fontSize="sm">
            Delete this {isIncome ? 'income' : 'expense'}? This can't be undone.
          </Text>
          <Button
            variant="ghost"
            onClick={() => setConfirmingDelete(false)}
            disabled={deleteMutation.isPending}
          >
            Keep
          </Button>
          <Button
            colorPalette="red"
            onClick={() => deleteMutation.mutate()}
            loading={deleteMutation.isPending}
            data-testid="delete-expense-confirm"
          >
            Delete
          </Button>
        </DialogFooter>
      ) : (
        <DialogFooter>
          <Button
            variant="ghost"
            colorPalette="red"
            mr="auto"
            onClick={() => setConfirmingDelete(true)}
            disabled={busy}
            data-testid="edit-expense-delete"
          >
            Delete
          </Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            colorPalette="brand"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!isValid || busy}
          >
            Save
          </Button>
        </DialogFooter>
      )}
    </>
  )
}

function EditExpenseDialog({ open, onOpenChange, familyId, expense }: EditExpenseDialogProps) {
  return (
    <DialogRoot
      open={open}
      onOpenChange={(e) => !e.open && onOpenChange(false)}
      placement={{ base: 'bottom', md: 'center' }}
      scrollBehavior="inside"
    >
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          {expense ? (
            <EditForm
              key={expense.id + expense.updated_at}
              expense={expense}
              familyId={familyId}
              onOpenChange={onOpenChange}
            />
          ) : (
            <DialogHeader>
              <DialogTitle>Edit Expense</DialogTitle>
            </DialogHeader>
          )}
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default EditExpenseDialog
