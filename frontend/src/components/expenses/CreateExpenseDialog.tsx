import { useEffect, useRef, useState } from 'react'
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
import { createExpense } from '../../api/expenses'
import { getCategories } from '../../api/categories'
import { toaster } from '../ui/toaster'

const LAST_USED_CATEGORY_KEY = 'lastUsedCategoryId'

interface CreateExpenseDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
}

function todayString(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function getDefaultCategoryId(categories: { id: string }[]): string {
  if (categories.length === 0) return ''
  const lastUsed = localStorage.getItem(LAST_USED_CATEGORY_KEY)
  if (lastUsed && categories.some((c) => c.id === lastUsed)) return lastUsed
  return categories[0].id
}

function CreateExpenseDialog({ open, onOpenChange, familyId }: CreateExpenseDialogProps) {
  const queryClient = useQueryClient()
  const amountRef = useRef<HTMLInputElement>(null)

  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [expenseDate, setExpenseDate] = useState(todayString)

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId),
    enabled: open,
  })

  // Derive effective category ID: prefer controlled state, fall back to default
  const effectiveCategoryId = categoryId || getDefaultCategoryId(categories)

  // Auto-focus amount input when dialog opens
  useEffect(() => {
    if (open) {
      setTimeout(() => {
        amountRef.current?.focus()
      }, 50)
    }
  }, [open])

  const mutation = useMutation({
    mutationFn: () => {
      const amountCents = Math.round(parseFloat(amount) * 100)
      return createExpense(familyId, {
        amount_cents: amountCents,
        description: description.trim() || undefined,
        category_id: effectiveCategoryId,
        expense_date: expenseDate,
      })
    },
    onSuccess: () => {
      localStorage.setItem(LAST_USED_CATEGORY_KEY, effectiveCategoryId)
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      toaster.create({
        title: 'Expense added',
        description: `$${parseFloat(amount).toFixed(2)} recorded successfully.`,
        type: 'success',
        duration: 4000,
      })
      handleClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to add expense. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  function handleClose() {
    setAmount('')
    setDescription('')
    setExpenseDate(todayString())
    setCategoryId('')
    onOpenChange(false)
  }

  const parsedAmount = parseFloat(amount)
  const isValid =
    amount.trim().length > 0 &&
    !isNaN(parsedAmount) &&
    parsedAmount > 0 &&
    effectiveCategoryId.length > 0 &&
    expenseDate.length > 0

  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && handleClose()} placement="center">
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Expense</DialogTitle>
          </DialogHeader>
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
                  ref={amountRef}
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  inputMode="decimal"
                  autoComplete="off"
                  disabled={mutation.isPending}
                  data-testid="expense-amount-input"
                />
              </Stack>
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  Description
                </Text>
                <Input
                  placeholder="e.g. Weekly groceries"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                  disabled={mutation.isPending}
                  data-testid="expense-description-input"
                />
              </Stack>
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  Category{' '}
                  <Text as="span" color="red.500">
                    *
                  </Text>
                </Text>
                <NativeSelectRoot disabled={mutation.isPending}>
                  <NativeSelectField
                    value={effectiveCategoryId}
                    onChange={(e) => setCategoryId(e.target.value)}
                    data-testid="expense-category-select"
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
                  data-testid="expense-date-input"
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
              data-testid="expense-submit-btn"
            >
              Add Expense
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default CreateExpenseDialog
