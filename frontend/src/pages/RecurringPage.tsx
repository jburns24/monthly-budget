import { useState } from 'react'
import { Badge, Box, Button, Container, Flex, Heading, Spinner, Text } from '@chakra-ui/react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useFamilyContext } from '../contexts/FamilyContext'
import {
  deleteRecurringExpense,
  getRecurringExpenses,
  updateRecurringExpense,
} from '../api/recurring'
import { getCategories } from '../api/categories'
import { FREQUENCY_LABELS, type RecurringExpense } from '../types/recurring'
import CreateRecurringDialog from '../components/recurring/CreateRecurringDialog'
import { toaster } from '../components/ui/toaster'

function formatAmount(amountCents: number): string {
  return `$${(amountCents / 100).toFixed(2)}`
}

function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function RecurringPage() {
  const { familyId } = useFamilyContext()
  const queryClient = useQueryClient()
  const [createOpen, setCreateOpen] = useState(false)

  const {
    data: rules,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['recurring', familyId],
    queryFn: () => getRecurringExpenses(familyId!),
    enabled: familyId !== null,
  })

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId!),
    enabled: familyId !== null,
  })

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ['recurring', familyId] })
    queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
    queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
  }

  const toggleMutation = useMutation({
    mutationFn: (rule: RecurringExpense) =>
      updateRecurringExpense(familyId!, rule.id, { is_active: !rule.is_active }),
    onSuccess: invalidate,
    onError: () =>
      toaster.create({
        title: 'Error',
        description: 'Could not update this recurring entry.',
        type: 'error',
        duration: 4000,
      }),
  })

  const deleteMutation = useMutation({
    mutationFn: (rule: RecurringExpense) => deleteRecurringExpense(familyId!, rule.id),
    onSuccess: () => {
      invalidate()
      toaster.create({ title: 'Recurring entry deleted', type: 'success', duration: 4000 })
    },
    onError: () =>
      toaster.create({
        title: 'Error',
        description: 'Failed to delete recurring entry.',
        type: 'error',
        duration: 4000,
      }),
  })

  function categoryLabel(rule: RecurringExpense): string {
    if (rule.entry_type === 'income') return 'Income'
    const cat = categories.find((c) => c.id === rule.category_id)
    return cat ? `${cat.icon ? `${cat.icon} ` : ''}${cat.name}` : 'Expense'
  }

  function handleDelete(rule: RecurringExpense) {
    const name = rule.description || categoryLabel(rule)
    if (window.confirm(`Delete "${name}"? Entries already added stay in your history.`)) {
      deleteMutation.mutate(rule)
    }
  }

  return (
    <Container maxW="1199px" px={{ base: 4, md: 8 }} py={{ base: 8, md: 16 }}>
      <Flex
        align={{ base: 'flex-end', md: 'center' }}
        justify="space-between"
        mb={{ base: 8, md: 12 }}
      >
        <Box>
          <Text
            color="ink.muted"
            fontSize="13px"
            fontWeight="500"
            textTransform="uppercase"
            letterSpacing="0.08em"
            mb={3}
          >
            Set once, applied automatically
          </Text>
          <Heading
            as="h1"
            fontFamily="heading"
            fontSize={{ base: '48px', md: '85px' }}
            fontWeight="500"
            lineHeight="0.95"
            letterSpacing={{ base: '-2.4px', md: '-4.25px' }}
            color="ink"
          >
            Recurring
          </Heading>
        </Box>
        {familyId && (
          <Button
            colorPalette="brand"
            borderRadius="pill"
            minH="44px"
            px={{ base: 4, md: 5 }}
            onClick={() => setCreateOpen(true)}
            data-testid="add-recurring-btn"
          >
            Add Recurring
          </Button>
        )}
      </Flex>

      {!familyId && (
        <Box py={12} textAlign="center">
          <Text color="gray.500">Create or join a family to set up recurring entries.</Text>
        </Box>
      )}

      {familyId && isLoading && (
        <Flex justify="center" py={12}>
          <Spinner size="lg" color="brand.500" aria-label="Loading recurring entries" />
        </Flex>
      )}

      {familyId && isError && (
        <Box py={8} textAlign="center">
          <Text color="red.500">Failed to load recurring entries. Please refresh the page.</Text>
        </Box>
      )}

      {rules && rules.length === 0 && (
        <Box py={12} textAlign="center" data-testid="recurring-empty">
          <Text color="ink.muted">
            Nothing recurring yet. Add rent, subscriptions, or a paycheck once and it shows up on
            schedule.
          </Text>
        </Box>
      )}

      {rules && rules.length > 0 && (
        <Flex direction="column" gap={3} data-testid="recurring-list">
          {rules.map((rule) => {
            const isIncome = rule.entry_type === 'income'
            return (
              <Flex
                key={rule.id}
                p={4}
                gap={4}
                align="center"
                justify="space-between"
                flexWrap="wrap"
                bg="surface.1"
                borderRadius="16px"
                borderWidth="1px"
                borderColor="hairline"
                opacity={rule.is_active ? 1 : 0.6}
                data-testid={`recurring-row-${rule.id}`}
              >
                <Box minW={0} flex="1">
                  <Flex align="center" gap={2} flexWrap="wrap">
                    <Text fontWeight="500" color="ink" truncate>
                      {rule.description || categoryLabel(rule)}
                    </Text>
                    <Badge size="sm" variant="subtle" color="ink.muted">
                      {FREQUENCY_LABELS[rule.frequency]}
                    </Badge>
                    {!rule.is_active && (
                      <Badge size="sm" variant="subtle" color="ink.muted">
                        Paused
                      </Badge>
                    )}
                  </Flex>
                  <Text fontSize="xs" color="ink.muted" mt={1}>
                    {categoryLabel(rule)}
                    {rule.is_active && ` · Next ${formatDate(rule.next_due_date)}`}
                    {rule.end_date && ` · Ends ${formatDate(rule.end_date)}`}
                  </Text>
                </Box>
                <Text
                  fontWeight="500"
                  fontVariantNumeric="tabular-nums"
                  color={isIncome ? 'income' : 'spend'}
                >
                  {isIncome ? '+' : ''}
                  {formatAmount(rule.amount_cents)}
                </Text>
                <Flex gap={2}>
                  <Button
                    size="sm"
                    bg="surface.2"
                    color="ink"
                    borderRadius="pill"
                    onClick={() => toggleMutation.mutate(rule)}
                    disabled={toggleMutation.isPending}
                    data-testid={`recurring-toggle-${rule.id}`}
                  >
                    {rule.is_active ? 'Pause' : 'Resume'}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    color="red.400"
                    borderRadius="pill"
                    onClick={() => handleDelete(rule)}
                    disabled={deleteMutation.isPending}
                    data-testid={`recurring-delete-${rule.id}`}
                  >
                    Delete
                  </Button>
                </Flex>
              </Flex>
            )
          })}
        </Flex>
      )}

      {familyId && (
        <CreateRecurringDialog open={createOpen} onOpenChange={setCreateOpen} familyId={familyId} />
      )}
    </Container>
  )
}

export default RecurringPage
