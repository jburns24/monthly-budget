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
import { createRecurringExpense } from '../../api/recurring'
import { getCategories } from '../../api/categories'
import type { EntryType } from '../../types/expenses'
import {
  FREQUENCY_LABELS,
  type Frequency,
  type RecurringExpenseCreate,
} from '../../types/recurring'
import { toaster } from '../ui/toaster'
import EntryTypeToggle from '../expenses/EntryTypeToggle'

interface CreateRecurringDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
}

function todayString(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

function CreateRecurringDialog({ open, onOpenChange, familyId }: CreateRecurringDialogProps) {
  const queryClient = useQueryClient()

  const [entryType, setEntryType] = useState<EntryType>('expense')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [frequency, setFrequency] = useState<Frequency>('monthly')
  const [startDate, setStartDate] = useState(todayString)
  const [endDate, setEndDate] = useState('')
  const isIncome = entryType === 'income'

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId),
    enabled: open,
  })
  const effectiveCategoryId = categoryId || categories[0]?.id || ''

  const mutation = useMutation({
    mutationFn: () => {
      const payload: RecurringExpenseCreate = {
        amount_cents: Math.round(parseFloat(amount) * 100),
        description: description.trim() || undefined,
        entry_type: entryType,
        frequency,
        start_date: startDate,
        end_date: endDate || null,
      }
      if (!isIncome) payload.category_id = effectiveCategoryId
      return createRecurringExpense(familyId, payload)
    },
    onSuccess: () => {
      // Creating a rule back-fills anything already due, so refresh the entries too.
      queryClient.invalidateQueries({ queryKey: ['recurring', familyId] })
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      toaster.create({
        title: 'Recurring entry saved',
        description: `${FREQUENCY_LABELS[frequency]} · $${parseFloat(amount).toFixed(2)}`,
        type: 'success',
        duration: 4000,
      })
      handleClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to save recurring entry. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  function handleClose() {
    setEntryType('expense')
    setAmount('')
    setDescription('')
    setCategoryId('')
    setFrequency('monthly')
    setStartDate(todayString())
    setEndDate('')
    onOpenChange(false)
  }

  const parsedAmount = parseFloat(amount)
  const isValid =
    amount.trim().length > 0 &&
    !isNaN(parsedAmount) &&
    parsedAmount > 0 &&
    startDate.length > 0 &&
    (!endDate || endDate >= startDate) &&
    (isIncome || effectiveCategoryId.length > 0)

  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && handleClose()} placement="center">
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Recurring {isIncome ? 'Income' : 'Expense'}</DialogTitle>
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
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  Amount{' '}
                  <Text as="span" color="red.500">
                    *
                  </Text>
                </Text>
                <Input
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  inputMode="decimal"
                  autoComplete="off"
                  disabled={mutation.isPending}
                  data-testid="recurring-amount-input"
                />
              </Stack>
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  Description
                </Text>
                <Input
                  placeholder={isIncome ? 'e.g. Paycheck' : 'e.g. Rent'}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={500}
                  disabled={mutation.isPending}
                  data-testid="recurring-description-input"
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
                      value={effectiveCategoryId}
                      onChange={(e) => setCategoryId(e.target.value)}
                      data-testid="recurring-category-select"
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
                  Repeats
                </Text>
                <NativeSelectRoot disabled={mutation.isPending}>
                  <NativeSelectField
                    value={frequency}
                    onChange={(e) => setFrequency(e.target.value as Frequency)}
                    data-testid="recurring-frequency-select"
                  >
                    {(Object.keys(FREQUENCY_LABELS) as Frequency[]).map((f) => (
                      <option key={f} value={f}>
                        {FREQUENCY_LABELS[f]}
                      </option>
                    ))}
                  </NativeSelectField>
                </NativeSelectRoot>
              </Stack>
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  First date{' '}
                  <Text as="span" color="red.500">
                    *
                  </Text>
                </Text>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  disabled={mutation.isPending}
                  data-testid="recurring-start-input"
                />
                <Text fontSize="xs" color="ink.muted">
                  Dates on or before today are added right away.
                </Text>
              </Stack>
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  Ends (optional)
                </Text>
                <Input
                  type="date"
                  value={endDate}
                  min={startDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  disabled={mutation.isPending}
                  data-testid="recurring-end-input"
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
              data-testid="recurring-submit-btn"
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default CreateRecurringDialog
