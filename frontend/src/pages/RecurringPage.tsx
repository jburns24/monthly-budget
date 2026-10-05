import { useState } from 'react'
import { Box, Button, Container, Flex, Heading, Spinner, Text } from '@chakra-ui/react'
import { useQuery } from '@tanstack/react-query'
import { useFamilyContext } from '../contexts/FamilyContext'
import { getRecurringExpenses } from '../api/recurring'
import { getCategories } from '../api/categories'
import { FREQUENCY_LABELS, type RecurringExpense } from '../types/recurring'
import CreateRecurringDialog from '../components/recurring/CreateRecurringDialog'
import EditRecurringDialog from '../components/recurring/EditRecurringDialog'
import { isEnded } from '../utils/recurrence'
import { formatCents } from '../utils/format'

function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  const showYear = year !== new Date().getFullYear()
  return new Date(year, month - 1, day).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(showYear ? { year: 'numeric' } : {}),
  })
}

/** Active rules first, then paused, then ended; stable within each group. */
function statusRank(rule: RecurringExpense): number {
  if (rule.is_active) return 0
  return isEnded(rule) ? 2 : 1
}

function PlusIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function EditIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

function RecurringPage() {
  const { familyId } = useFamilyContext()
  const [createOpen, setCreateOpen] = useState(false)
  const [editRule, setEditRule] = useState<RecurringExpense | null>(null)

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

  const sortedRules = rules ? [...rules].sort((x, y) => statusRank(x) - statusRank(y)) : undefined

  function category(rule: RecurringExpense) {
    return categories.find((c) => c.id === rule.category_id)
  }

  function title(rule: RecurringExpense): string {
    if (rule.description) return rule.description
    if (rule.entry_type === 'income') return 'Income'
    return category(rule)?.name ?? 'Expense'
  }

  function metaLine(rule: RecurringExpense): string {
    const parts = [FREQUENCY_LABELS[rule.frequency]]
    if (isEnded(rule)) parts.unshift('Ended')
    else if (!rule.is_active) parts.unshift('Paused')
    else parts.push(`Next ${formatDate(rule.next_due_date)}`)
    if (rule.is_active && rule.end_date) parts.push(`until ${formatDate(rule.end_date)}`)
    return parts.join(' · ')
  }

  return (
    <Container
      maxW="1199px"
      px={{ base: 4, md: 8 }}
      pt={{ base: 4, md: 16 }}
      pb={{ base: '120px', md: 16 }}
    >
      <Flex align="center" justify="space-between" gap={3} mb={{ base: 4, md: 12 }}>
        <Box minW={0}>
          <Text
            display={{ base: 'none', md: 'block' }}
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
            fontSize={{ base: '28px', md: '85px' }}
            fontWeight="500"
            lineHeight="0.95"
            letterSpacing={{ base: '-1px', md: '-4.25px' }}
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
            minW="44px"
            px={{ base: 0, md: 5 }}
            flexShrink={0}
            onClick={() => setCreateOpen(true)}
            aria-label="Add recurring"
            data-testid="add-recurring-btn"
          >
            <Box display={{ base: 'inline-flex', md: 'none' }}>
              <PlusIcon />
            </Box>
            <Box as="span" display={{ base: 'none', md: 'inline' }}>
              Add Recurring
            </Box>
          </Button>
        )}
      </Flex>

      {!familyId && (
        <Box py={12} textAlign="center">
          <Text color="ink.muted">Create or join a family to set up recurring entries.</Text>
        </Box>
      )}

      {familyId && isLoading && (
        <Flex justify="center" py={12}>
          <Spinner size="lg" color="brand.500" aria-label="Loading recurring entries" />
        </Flex>
      )}

      {familyId && isError && (
        <Box py={8} textAlign="center">
          <Text color="spend">Failed to load recurring entries. Please refresh the page.</Text>
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

      {sortedRules && sortedRules.length > 0 && (
        <Flex direction="column" gap={2} maxW={{ md: '720px' }} data-testid="recurring-list">
          {sortedRules.map((rule) => {
            const isIncome = rule.entry_type === 'income'
            const inactive = !rule.is_active
            const name = title(rule)
            return (
              <Flex
                key={rule.id}
                align="center"
                p={3}
                gap={3}
                bg="surface.1"
                borderRadius="card"
                borderWidth="1px"
                borderColor="hairline"
                data-testid={`recurring-row-${rule.id}`}
              >
                <Flex
                  align="center"
                  justify="center"
                  w="40px"
                  h="40px"
                  flexShrink={0}
                  borderRadius="10px"
                  bg="surface.2"
                  borderWidth="1px"
                  borderColor="hairline"
                  fontSize="xl"
                  opacity={inactive ? 0.55 : 1}
                  aria-hidden="true"
                >
                  {isIncome ? '💵' : (category(rule)?.icon ?? '📁')}
                </Flex>
                <Box flex={1} minW={0}>
                  <Text fontWeight="500" color="ink" truncate>
                    {name}
                  </Text>
                  <Text
                    fontSize="xs"
                    color="ink.muted"
                    truncate
                    data-testid={`recurring-meta-${rule.id}`}
                  >
                    {metaLine(rule)}
                  </Text>
                </Box>
                <Text
                  fontWeight="500"
                  fontSize={{ base: 'sm', md: 'md' }}
                  fontVariantNumeric="tabular-nums"
                  whiteSpace="nowrap"
                  flexShrink={0}
                  color={isIncome ? 'income' : 'spend'}
                  opacity={inactive ? 0.55 : 1}
                >
                  {isIncome ? '+' : '−'}
                  {formatCents(rule.amount_cents)}
                </Text>
                <Button
                  bg="surface.2"
                  color="ink"
                  borderRadius="full"
                  w="44px"
                  h="44px"
                  minW="44px"
                  p={0}
                  flexShrink={0}
                  _hover={{ bg: 'surface.3' }}
                  onClick={() => setEditRule(rule)}
                  aria-label={`Edit ${name}`}
                  data-testid={`recurring-edit-${rule.id}`}
                >
                  <EditIcon />
                </Button>
              </Flex>
            )
          })}
        </Flex>
      )}

      {familyId && (
        <>
          <CreateRecurringDialog
            open={createOpen}
            onOpenChange={setCreateOpen}
            familyId={familyId}
          />
          <EditRecurringDialog
            open={editRule !== null}
            onOpenChange={(open) => !open && setEditRule(null)}
            familyId={familyId}
            rule={editRule}
          />
        </>
      )}
    </Container>
  )
}

export default RecurringPage
