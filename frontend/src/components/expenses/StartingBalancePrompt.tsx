import { useState } from 'react'
import { Box, Button, Flex, Input, Text } from '@chakra-ui/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { createExpense } from '../../api/expenses'
import { toaster } from '../ui/toaster'

export interface StartingBalancePromptProps {
  familyId: string
  yearMonth: string
  hasStartingBalance: boolean
}

function formatMonth(yearMonth: string): string {
  const [year, month] = yearMonth.split('-')
  if (!year || !month) return yearMonth
  const date = new Date(parseInt(year, 10), parseInt(month, 10) - 1, 1)
  return date.toLocaleString('default', { month: 'long', year: 'numeric' })
}

function todayYearMonth(now = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

function todayString(now = new Date()): string {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** First of month, or today when `yearMonth` is the current calendar month. */
function startingBalanceExpenseDate(yearMonth: string, now = new Date()): string {
  if (yearMonth === todayYearMonth(now)) {
    return todayString(now)
  }
  return `${yearMonth}-01`
}

function StartingBalancePrompt({
  familyId,
  yearMonth,
  hasStartingBalance,
}: StartingBalancePromptProps) {
  const queryClient = useQueryClient()
  const [dismissed, setDismissed] = useState(false)
  const [amount, setAmount] = useState('')

  const parsedAmount = parseFloat(amount)
  const isValid = amount.trim().length > 0 && !isNaN(parsedAmount) && parsedAmount > 0

  const mutation = useMutation({
    mutationFn: () => {
      const amountCents = Math.round(parsedAmount * 100)
      return createExpense(familyId, {
        amount_cents: amountCents,
        description: 'Starting balance',
        expense_date: startingBalanceExpenseDate(yearMonth),
        entry_type: 'income',
        is_starting_balance: true,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId, yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
      toaster.create({
        title: 'Starting balance set',
        description: `$${parsedAmount.toFixed(2)} recorded for ${formatMonth(yearMonth)}.`,
        type: 'success',
        duration: 4000,
      })
      setDismissed(true)
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to set starting balance. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  if (hasStartingBalance || dismissed) {
    return null
  }

  return (
    <Box
      data-testid="starting-balance-prompt"
      borderWidth="1px"
      borderColor="hairline"
      borderRadius="card"
      bg="surface.1"
      p={4}
    >
      <Flex align="center" gap={3} wrap="wrap">
        <Text fontSize="sm" flex="1" minW="180px">
          Set a starting balance for {formatMonth(yearMonth)}?
        </Text>
        <Input
          data-testid="starting-balance-amount-input"
          placeholder="0.00"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          inputMode="decimal"
          autoComplete="off"
          disabled={mutation.isPending}
          maxW="140px"
          size="sm"
          aria-label="Starting balance amount"
        />
        <Button
          data-testid="starting-balance-submit-btn"
          size="sm"
          colorPalette="brand"
          borderRadius="pill"
          onClick={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!isValid || mutation.isPending}
        >
          Set balance
        </Button>
        <Button
          data-testid="starting-balance-skip-btn"
          size="sm"
          variant="ghost"
          onClick={() => setDismissed(true)}
          disabled={mutation.isPending}
        >
          Skip for now
        </Button>
      </Flex>
    </Box>
  )
}

export default StartingBalancePrompt
