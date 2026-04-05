import { useState } from 'react'
import { Button, Input, Stack, Text, Flex } from '@chakra-ui/react'
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
import { updateGoalsBulk } from '../../api/goals'
import type { MonthlyGoal } from '../../types/goals'
import type { Category } from '../../types/categories'
import { toaster } from '../ui/toaster'

export interface BulkGoalsEditorProps {
  isOpen: boolean
  onClose: () => void
  familyId: string
  yearMonth: string
  categories: Category[]
  currentGoals: MonthlyGoal[]
}

function BulkGoalsEditor({
  isOpen,
  onClose,
  familyId,
  yearMonth,
  categories,
  currentGoals,
}: BulkGoalsEditorProps) {
  const queryClient = useQueryClient()

  // Build initial amounts map: category_id -> dollar string
  function buildInitialAmounts(): Record<string, string> {
    const map: Record<string, string> = {}
    for (const cat of categories) {
      const goal = currentGoals.find((g) => g.category_id === cat.id)
      map[cat.id] = goal ? (goal.amount_cents / 100).toFixed(2) : ''
    }
    return map
  }

  const [amounts, setAmounts] = useState<Record<string, string>>(buildInitialAmounts)

  const mutation = useMutation({
    mutationFn: () => {
      const goals = categories
        .filter((cat) => {
          const val = amounts[cat.id]
          if (!val || val.trim() === '') return false
          const parsed = parseFloat(val)
          return !isNaN(parsed) && parsed > 0
        })
        .map((cat) => ({
          category_id: cat.id,
          amount_cents: Math.round(parseFloat(amounts[cat.id]) * 100),
        }))

      return updateGoalsBulk(familyId, {
        year_month: yearMonth,
        goals,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', familyId, yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId, yearMonth] })
      toaster.create({
        title: 'Goals saved',
        description: 'Monthly goals have been updated.',
        type: 'success',
        duration: 4000,
      })
      handleClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to save goals. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  function handleClose() {
    setAmounts(buildInitialAmounts())
    onClose()
  }

  function handleAmountChange(categoryId: string, value: string) {
    setAmounts((prev) => ({ ...prev, [categoryId]: value }))
  }

  return (
    <DialogRoot open={isOpen} onOpenChange={(e) => !e.open && handleClose()}>
      <DialogBackdrop />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit Monthly Goals</DialogTitle>
        </DialogHeader>
        <DialogBody>
          <Stack gap={3}>
            <Text fontSize="sm" color="gray.500">
              Set monthly spending limits for each category. Leave blank to remove a goal.
            </Text>
            {categories.map((cat) => (
              <Flex key={cat.id} align="center" gap={3}>
                <Text flex="1" fontSize="sm" fontWeight="medium">
                  {cat.icon ? `${cat.icon} ` : ''}
                  {cat.name}
                </Text>
                <Input
                  data-testid={`goal-input-${cat.id}`}
                  type="number"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={amounts[cat.id] ?? ''}
                  onChange={(e) => handleAmountChange(cat.id, e.target.value)}
                  min="0.01"
                  step="0.01"
                  disabled={mutation.isPending}
                  width="140px"
                  aria-label={`Monthly goal for ${cat.name}`}
                />
              </Flex>
            ))}
          </Stack>
        </DialogBody>
        <DialogFooter>
          <Button variant="ghost" onClick={handleClose} disabled={mutation.isPending}>
            Cancel
          </Button>
          <Button
            colorPalette="brand"
            data-testid="bulk-goals-save-btn"
            onClick={() => mutation.mutate()}
            loading={mutation.isPending}
          >
            Save All
          </Button>
        </DialogFooter>
      </DialogContent>
    </DialogRoot>
  )
}

export default BulkGoalsEditor
