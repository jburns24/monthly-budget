import { useState } from 'react'
import { Box, Button, Flex, Text } from '@chakra-ui/react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { rolloverGoals } from '../../api/goals'
import { toaster } from '../ui/toaster'

export interface RolloverPromptProps {
  familyId: string
  yearMonth: string
  hasPreviousGoals: boolean
  previousMonth: string
  onRolloverComplete: () => void
}

function formatMonth(yearMonth: string): string {
  const [year, month] = yearMonth.split('-')
  if (!year || !month) return yearMonth
  const date = new Date(parseInt(year, 10), parseInt(month, 10) - 1, 1)
  return date.toLocaleString('default', { month: 'long', year: 'numeric' })
}

function RolloverPrompt({
  familyId,
  yearMonth,
  hasPreviousGoals,
  previousMonth,
  onRolloverComplete,
}: RolloverPromptProps) {
  const queryClient = useQueryClient()
  const [dismissed, setDismissed] = useState(false)

  const mutation = useMutation({
    mutationFn: () =>
      rolloverGoals(familyId, {
        source_month: previousMonth,
        target_month: yearMonth,
      }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['goals', familyId, yearMonth] })
      queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId, yearMonth] })
      toaster.create({
        title: 'Goals copied',
        description: `Copied ${data.copied_count} goal${data.copied_count !== 1 ? 's' : ''} from ${formatMonth(previousMonth)}.`,
        type: 'success',
        duration: 4000,
      })
      onRolloverComplete()
    },
    onError: () => {
      toaster.create({
        title: 'Error',
        description: 'Failed to copy goals. Please try again.',
        type: 'error',
        duration: 4000,
      })
    },
  })

  if (!hasPreviousGoals || dismissed) {
    return null
  }

  const currentMonthLabel = formatMonth(yearMonth)
  const previousMonthLabel = formatMonth(previousMonth)

  return (
    <Box
      data-testid="rollover-prompt"
      borderWidth="1px"
      borderColor="blue.200"
      borderRadius="md"
      bg="blue.50"
      p={4}
    >
      <Flex align="center" gap={3} wrap="wrap">
        <Text fontSize="sm" flex="1">
          No goals set for {currentMonthLabel}.
        </Text>
        <Button
          data-testid="rollover-copy-btn"
          size="sm"
          colorPalette="blue"
          onClick={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={mutation.isPending}
        >
          Copy from {previousMonthLabel}
        </Button>
        <Button
          data-testid="rollover-start-fresh-btn"
          size="sm"
          variant="ghost"
          onClick={() => setDismissed(true)}
          disabled={mutation.isPending}
        >
          Start Fresh
        </Button>
      </Flex>
    </Box>
  )
}

export default RolloverPrompt
