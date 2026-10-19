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
import { createRecurringExpense } from '../../api/recurring'
import { getCategories, suggestCategory } from '../../api/categories'
import { invalidateAssets } from '../../hooks/useAssets'
import type { EntryType, ExpenseCreate } from '../../types/expenses'
import { toaster } from '../ui/toaster'
import type { Frequency } from '../../types/recurring'
import EntryTypeToggle from './EntryTypeToggle'
import RepeatFields from './RepeatFields'
import AssetLinkFields from '../assets/AssetLinkFields'
import { NO_ASSET_LINK, assetLinkFields, type AssetLink } from '../assets/assetLink'

const LAST_USED_CATEGORY_KEY = 'lastUsedCategoryId'
// Shorter descriptions are too ambiguous to be worth a suggestion round-trip.
const MIN_SUGGEST_LENGTH = 3

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
  const descriptionRef = useRef<HTMLInputElement>(null)
  // In-flight suggestion request, aborted when a newer one starts or the dialog closes.
  const suggestAbortRef = useRef<AbortController | null>(null)
  const lastSuggestedRef = useRef('')
  // Once the user picks a category by hand, suggestions never override it this session.
  const userPickedCategoryRef = useRef(false)

  const [entryType, setEntryType] = useState<EntryType>('expense')
  const [amount, setAmount] = useState('')
  const [description, setDescription] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [expenseDate, setExpenseDate] = useState(todayString)
  const [repeat, setRepeat] = useState(false)
  const [frequency, setFrequency] = useState<Frequency>('monthly')
  const [endDate, setEndDate] = useState('')
  const [assetLink, setAssetLink] = useState<AssetLink>(NO_ASSET_LINK)
  const isIncome = entryType === 'income'

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId),
    enabled: open,
  })

  // Derive effective category ID: prefer controlled state, fall back to default
  const effectiveCategoryId = categoryId || getDefaultCategoryId(categories)

  // Auto-focus the description input when the dialog opens: it is typed first so
  // its category suggestion can land while the user enters the amount.
  useEffect(() => {
    if (open) {
      setTimeout(() => {
        descriptionRef.current?.focus()
      }, 50)
    }
  }, [open])

  // Never let a late suggestion apply after the dialog has gone away.
  useEffect(() => () => suggestAbortRef.current?.abort(), [])

  function handleDescriptionBlur() {
    const text = description.trim()
    if (isIncome || userPickedCategoryRef.current) return
    if (text.length < MIN_SUGGEST_LENGTH || text === lastSuggestedRef.current) return
    lastSuggestedRef.current = text

    suggestAbortRef.current?.abort()
    const controller = new AbortController()
    suggestAbortRef.current = controller

    suggestCategory(familyId, text, controller.signal)
      .then((suggestion) => {
        if (controller.signal.aborted || userPickedCategoryRef.current) return
        const id = suggestion?.category_id
        if (id && categories.some((c) => c.id === id)) {
          // Replaces the default, including the localStorage last-used one.
          setCategoryId(id)
        }
      })
      .catch(() => {
        // No suggestion (network error, abort, rate limit): keep the current default.
      })
  }

  const mutation = useMutation({
    mutationFn: async () => {
      const amountCents = Math.round(parseFloat(amount) * 100)
      if (repeat) {
        await createRecurringExpense(familyId, {
          amount_cents: amountCents,
          description: description.trim() || undefined,
          entry_type: entryType,
          frequency,
          start_date: expenseDate,
          end_date: endDate || null,
          ...(isIncome ? {} : { category_id: effectiveCategoryId }),
          ...assetLinkFields(assetLink, isIncome),
        })
        return
      }
      const payload: ExpenseCreate = {
        amount_cents: amountCents,
        description: description.trim() || undefined,
        expense_date: expenseDate,
        entry_type: entryType,
      }
      if (!isIncome) {
        payload.category_id = effectiveCategoryId
      }
      Object.assign(payload, assetLinkFields(assetLink, isIncome))
      await createExpense(familyId, payload)
    },
    onSuccess: () => {
      if (!isIncome) {
        localStorage.setItem(LAST_USED_CATEGORY_KEY, effectiveCategoryId)
      }
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
      if (repeat) queryClient.invalidateQueries({ queryKey: ['recurring', familyId] })
      if (assetLink.assetId && !isIncome) invalidateAssets(queryClient, familyId)
      toaster.create({
        title: repeat ? 'Recurring entry saved' : isIncome ? 'Income added' : 'Expense added',
        description: `$${parseFloat(amount).toFixed(2)} recorded successfully.`,
        type: 'success',
        duration: 4000,
      })
      handleClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: isIncome
          ? 'Failed to add income. Please try again.'
          : 'Failed to add expense. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  function handleClose() {
    suggestAbortRef.current?.abort()
    suggestAbortRef.current = null
    lastSuggestedRef.current = ''
    userPickedCategoryRef.current = false
    setEntryType('expense')
    setAmount('')
    setDescription('')
    setExpenseDate(todayString())
    setCategoryId('')
    setRepeat(false)
    setFrequency('monthly')
    setEndDate('')
    setAssetLink(NO_ASSET_LINK)
    onOpenChange(false)
  }

  const parsedAmount = parseFloat(amount)
  const isValid =
    amount.trim().length > 0 &&
    !isNaN(parsedAmount) &&
    parsedAmount > 0 &&
    expenseDate.length > 0 &&
    (!repeat || !endDate || endDate >= expenseDate) &&
    (isIncome || effectiveCategoryId.length > 0)

  return (
    <DialogRoot
      open={open}
      onOpenChange={(e) => !e.open && handleClose()}
      placement={{ base: 'bottom', md: 'center' }}
      scrollBehavior="inside"
    >
      <DialogBackdrop />
      <DialogPositioner>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{isIncome ? 'Add Income' : 'Add Expense'}</DialogTitle>
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
                minEndDate={expenseDate}
                disabled={mutation.isPending}
              />
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  Description
                </Text>
                <Input
                  placeholder={isIncome ? 'e.g. Paycheck' : 'e.g. Weekly groceries'}
                  value={description}
                  ref={descriptionRef}
                  onChange={(e) => setDescription(e.target.value)}
                  onBlur={handleDescriptionBlur}
                  maxLength={500}
                  disabled={mutation.isPending}
                  data-testid="expense-description-input"
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
                  data-testid="expense-amount-input"
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
                      onChange={(e) => {
                        userPickedCategoryRef.current = true
                        suggestAbortRef.current?.abort()
                        setCategoryId(e.target.value)
                      }}
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
              )}
              {!isIncome && (
                <AssetLinkFields
                  familyId={familyId}
                  value={assetLink}
                  onChange={setAssetLink}
                  recurring={repeat}
                  enabled={open}
                  disabled={mutation.isPending}
                />
              )}
              <Stack gap={1}>
                <Text fontWeight="medium" fontSize="sm">
                  {repeat ? 'First date' : 'Date'}{' '}
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
              {isIncome ? 'Add Income' : 'Add Expense'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </DialogPositioner>
    </DialogRoot>
  )
}

export default CreateExpenseDialog
