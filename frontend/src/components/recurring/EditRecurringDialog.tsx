import { useState } from 'react'
import {
  Button,
  Flex,
  Input,
  NativeSelectField,
  NativeSelectRoot,
  SimpleGrid,
  Stack,
  Text,
} from '@chakra-ui/react'
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
import { deleteRecurringExpense, updateRecurringExpense } from '../../api/recurring'
import { getCategories } from '../../api/categories'
import { FREQUENCY_LABELS, type Frequency, type RecurringExpense } from '../../types/recurring'
import type { RecurringExpenseUpdate } from '../../types/recurring'
import { toaster } from '../ui/toaster'
import { isEnded } from '../../utils/recurrence'

interface EditRecurringDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
  rule: RecurringExpense | null
}

function todayString(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

interface EditFormProps {
  rule: RecurringExpense
  familyId: string
  onOpenChange: (open: boolean) => void
}

function EditForm({ rule, familyId, onOpenChange }: EditFormProps) {
  const queryClient = useQueryClient()
  const isIncome = rule.entry_type === 'income'
  const [amount, setAmount] = useState(String(rule.amount_cents / 100))
  const [description, setDescription] = useState(rule.description)
  const [categoryId, setCategoryId] = useState(rule.category_id ?? '')
  const [frequency, setFrequency] = useState<Frequency>(rule.frequency)
  const [nextDate, setNextDate] = useState(rule.next_due_date)
  const [endDate, setEndDate] = useState(rule.end_date ?? '')
  const [confirmingDelete, setConfirmingDelete] = useState(false)

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId),
  })
  // The rule's category may have been archived since; force an explicit new pick then.
  const categoryMissing =
    !isIncome && categories.length > 0 && !categories.some((c) => c.id === categoryId)

  const mutation = useMutation({
    mutationFn: () => {
      const payload: RecurringExpenseUpdate = {}
      const cents = Math.round(parseFloat(amount) * 100)
      if (cents !== rule.amount_cents) payload.amount_cents = cents
      if (description.trim() !== rule.description) payload.description = description.trim()
      if (!isIncome && categoryId !== rule.category_id) payload.category_id = categoryId
      if (frequency !== rule.frequency) payload.frequency = frequency
      if (nextDate !== rule.next_due_date) payload.next_due_date = nextDate
      if (endDate !== (rule.end_date ?? '')) payload.end_date = endDate || null
      return updateRecurringExpense(familyId, rule.id, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recurring', familyId] })
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      toaster.create({ title: 'Recurring entry updated', type: 'success', duration: 4000 })
      onOpenChange(false)
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to update recurring entry. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['recurring', familyId] })
    queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
    queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
  }

  const toggleMutation = useMutation({
    mutationFn: () => updateRecurringExpense(familyId, rule.id, { is_active: !rule.is_active }),
    onSuccess: () => {
      refresh()
      toaster.create({
        title: rule.is_active ? 'Recurring entry paused' : 'Recurring entry resumed',
        type: 'success',
        duration: 4000,
      })
      onOpenChange(false)
    },
    onError: () =>
      toaster.create({
        title: 'Error',
        description: 'Could not update this recurring entry.',
        type: 'error',
        duration: 4000,
      }),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteRecurringExpense(familyId, rule.id),
    onSuccess: () => {
      refresh()
      toaster.create({ title: 'Recurring entry deleted', type: 'success', duration: 4000 })
      onOpenChange(false)
    },
    onError: () =>
      toaster.create({
        title: 'Error',
        description: 'Failed to delete recurring entry.',
        type: 'error',
        duration: 4000,
      }),
  })
  const busy = mutation.isPending || toggleMutation.isPending || deleteMutation.isPending

  const cents = Math.round(parseFloat(amount) * 100)
  const nextChanged = nextDate !== rule.next_due_date
  // A moved date must be in the future: earlier dates may already have entries.
  const nextValid = nextDate.length > 0 && (!nextChanged || nextDate > todayString())
  const endValid = !endDate || endDate >= nextDate
  const isValid =
    amount.trim().length > 0 &&
    !isNaN(cents) &&
    cents > 0 &&
    nextValid &&
    endValid &&
    (isIncome || (categoryId.length > 0 && !categoryMissing))

  const ended = isEnded(rule)
  const reviving = ended && endDate !== (rule.end_date ?? '') && endValid

  return (
    <>
      <DialogHeader>
        <DialogTitle>Edit Recurring {isIncome ? 'Income' : 'Expense'}</DialogTitle>
      </DialogHeader>
      <DialogBody>
        <Stack gap={4}>
          <Text fontSize="xs" color="ink.muted">
            Applies to future entries only.
          </Text>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Amount{' '}
              <Text as="span" color="red.500">
                *
              </Text>
            </Text>
            <Input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="decimal"
              autoComplete="off"
              disabled={mutation.isPending}
              data-testid="edit-recurring-amount"
            />
          </Stack>
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Description
            </Text>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              disabled={mutation.isPending}
              data-testid="edit-recurring-description"
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
                  value={categoryMissing ? '' : categoryId}
                  onChange={(e) => setCategoryId(e.target.value)}
                  data-testid="edit-recurring-category"
                >
                  {categoryMissing && (
                    <option value="" disabled>
                      Choose a category
                    </option>
                  )}
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>
                      {cat.icon ? `${cat.icon} ` : ''}
                      {cat.name}
                    </option>
                  ))}
                </NativeSelectField>
              </NativeSelectRoot>
              {categoryMissing && (
                <Text fontSize="xs" color="spend" data-testid="edit-recurring-category-hint">
                  This entry&apos;s category was archived. Pick another to keep it running.
                </Text>
              )}
            </Stack>
          )}
          <SimpleGrid columns={2} gap={3}>
            <Stack gap={1}>
              <Text fontWeight="medium" fontSize="sm">
                Repeats
              </Text>
              <NativeSelectRoot disabled={mutation.isPending}>
                <NativeSelectField
                  value={frequency}
                  onChange={(e) => setFrequency(e.target.value as Frequency)}
                  data-testid="edit-recurring-frequency"
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
                Next date{' '}
                <Text as="span" color="red.500">
                  *
                </Text>
              </Text>
              <Input
                type="date"
                value={nextDate}
                onChange={(e) => setNextDate(e.target.value)}
                disabled={mutation.isPending}
                data-testid="edit-recurring-next"
              />
            </Stack>
          </SimpleGrid>
          {frequency !== rule.frequency && (
            <Text fontSize="xs" color="ink.muted" data-testid="edit-recurring-frequency-hint">
              The schedule restarts from the next date.
            </Text>
          )}
          {!nextValid && (
            <Text fontSize="xs" color="spend" data-testid="edit-recurring-next-hint">
              Pick a date after today.
            </Text>
          )}
          <Stack gap={1}>
            <Text fontWeight="medium" fontSize="sm">
              Ends (optional)
            </Text>
            <Input
              type="date"
              value={endDate}
              min={nextDate}
              onChange={(e) => setEndDate(e.target.value)}
              disabled={mutation.isPending}
              data-testid="edit-recurring-end"
            />
            {!endValid && (
              <Text fontSize="xs" color="spend" data-testid="edit-recurring-end-hint">
                The end date can&apos;t be before the next date.
              </Text>
            )}
            {ended && (
              <Text fontSize="xs" color="ink.muted">
                {reviving
                  ? 'This will start the entry running again.'
                  : 'This entry has ended. Extend or clear the end date to run it again.'}
              </Text>
            )}
          </Stack>
          <Flex gap={2} pt={1}>
            {!ended && (
              <Button
                flex={1}
                bg="surface.2"
                color="ink"
                borderRadius="pill"
                minH="44px"
                onClick={() => toggleMutation.mutate()}
                loading={toggleMutation.isPending}
                disabled={busy}
                data-testid="edit-recurring-toggle"
              >
                {rule.is_active ? 'Pause' : 'Resume'}
              </Button>
            )}
            <Button
              flex={1}
              variant="ghost"
              colorPalette="red"
              borderRadius="pill"
              minH="44px"
              onClick={() => setConfirmingDelete(true)}
              disabled={busy}
              data-testid="edit-recurring-delete"
            >
              Delete
            </Button>
          </Flex>
        </Stack>
      </DialogBody>
      {confirmingDelete ? (
        <DialogFooter flexWrap="wrap">
          <Text mr="auto" fontSize="sm">
            Delete this recurring entry? Entries already added stay in your history.
          </Text>
          <Button
            variant="ghost"
            minH="44px"
            onClick={() => setConfirmingDelete(false)}
            disabled={deleteMutation.isPending}
          >
            Keep
          </Button>
          <Button
            colorPalette="red"
            minH="44px"
            onClick={() => deleteMutation.mutate()}
            loading={deleteMutation.isPending}
            data-testid="edit-recurring-delete-confirm"
          >
            Delete
          </Button>
        </DialogFooter>
      ) : (
        <DialogFooter>
          <Button variant="ghost" minH="44px" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            colorPalette="brand"
            minH="44px"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
            disabled={!isValid || busy}
            data-testid="edit-recurring-save"
          >
            Save
          </Button>
        </DialogFooter>
      )}
    </>
  )
}

function EditRecurringDialog({ open, onOpenChange, familyId, rule }: EditRecurringDialogProps) {
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
          {rule ? (
            <EditForm
              key={rule.id + rule.updated_at}
              rule={rule}
              familyId={familyId}
              onOpenChange={onOpenChange}
            />
          ) : (
            <DialogHeader>
              <DialogTitle>Edit Recurring</DialogTitle>
            </DialogHeader>
          )}
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default EditRecurringDialog
