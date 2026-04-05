import { useEffect, useRef, useState } from 'react'
import { Button, Input, Stack, Text } from '@chakra-ui/react'
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
import { updateGoal, updateGoalsBulk } from '../../api/goals'
import type { MonthlyGoal } from '../../types/goals'
import { toaster } from '../ui/toaster'

export interface SetGoalDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  familyId: string
  yearMonth: string
  categoryId: string
  categoryName: string
  existingGoal?: MonthlyGoal | null
}

interface GoalFormProps {
  familyId: string
  yearMonth: string
  categoryId: string
  categoryName: string
  existingGoal?: MonthlyGoal | null
  onClose: () => void
}

function GoalForm({
  familyId,
  yearMonth,
  categoryId,
  categoryName,
  existingGoal,
  onClose,
}: GoalFormProps) {
  const queryClient = useQueryClient()
  const amountRef = useRef<HTMLInputElement>(null)
  const initialAmount = existingGoal ? (existingGoal.amount_cents / 100).toFixed(2) : ''
  const [amount, setAmount] = useState(initialAmount)

  // Auto-focus the amount input on mount
  useEffect(() => {
    const id = setTimeout(() => {
      amountRef.current?.focus()
    }, 50)
    return () => clearTimeout(id)
  }, [])

  const mutation = useMutation({
    mutationFn: () => {
      const amountCents = Math.round(parseFloat(amount) * 100)
      if (existingGoal) {
        return updateGoal(familyId, existingGoal.id, {
          amount_cents: amountCents,
          expected_version: existingGoal.version,
        })
      } else {
        return updateGoalsBulk(familyId, {
          year_month: yearMonth,
          goals: [{ category_id: categoryId, amount_cents: amountCents }],
        }).then((res) => res.goals[0])
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['goals', familyId, yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId, yearMonth] })
      toaster.create({
        title: existingGoal ? 'Goal updated' : 'Goal set',
        description: `Monthly goal for "${categoryName}" has been ${existingGoal ? 'updated' : 'set'}.`,
        type: 'success',
        duration: 4000,
      })
      onClose()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: `Failed to ${existingGoal ? 'update' : 'set'} goal. Please try again.`,
        type: 'error',
        duration: 4000,
      })
    },
  })

  const parsedAmount = parseFloat(amount)
  const isValid = !isNaN(parsedAmount) && parsedAmount > 0

  return (
    <>
      <DialogBody>
        <Stack gap={3}>
          <Text fontSize="sm" color="gray.500">
            Monthly spending limit
          </Text>
          <Input
            ref={amountRef}
            data-testid="goal-amount-input"
            type="number"
            inputMode="decimal"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            min="0.01"
            step="0.01"
            disabled={mutation.isPending}
            aria-label="Monthly spending limit in dollars"
          />
        </Stack>
      </DialogBody>
      <DialogFooter>
        <Button variant="ghost" onClick={onClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button
          colorPalette="brand"
          data-testid="goal-save-btn"
          onClick={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!isValid}
        >
          Save Goal
        </Button>
      </DialogFooter>
    </>
  )
}

function SetGoalDialog({
  open,
  onOpenChange,
  familyId,
  yearMonth,
  categoryId,
  categoryName,
  existingGoal,
}: SetGoalDialogProps) {
  function handleClose() {
    onOpenChange(false)
  }

  const dialogTitle = existingGoal ? `Edit Goal — ${categoryName}` : `Set Goal — ${categoryName}`

  return (
    <DialogRoot open={open} onOpenChange={(e) => !e.open && handleClose()}>
      <DialogBackdrop />
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{dialogTitle}</DialogTitle>
        </DialogHeader>
        {open && (
          <GoalForm
            key={`${categoryId}-${existingGoal?.id ?? 'new'}-${open ? 'open' : 'closed'}`}
            familyId={familyId}
            yearMonth={yearMonth}
            categoryId={categoryId}
            categoryName={categoryName}
            existingGoal={existingGoal}
            onClose={handleClose}
          />
        )}
      </DialogContent>
    </DialogRoot>
  )
}

export default SetGoalDialog
