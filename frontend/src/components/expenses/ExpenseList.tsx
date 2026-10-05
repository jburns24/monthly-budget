import { Box, Button, Flex, Text } from '@chakra-ui/react'
import type { Expense } from '../../types/expenses'
import { formatCents } from '../../utils/format'

interface ExpenseListProps {
  expenses: Expense[]
  onEdit: (expense: Expense) => void
}

function formatSignedAmount(amountCents: number, entryType: Expense['entry_type']): string {
  const formatted = formatCents(amountCents)
  return entryType === 'income' ? `+${formatted}` : `−${formatted}`
}

function formatDate(dateString: string): string {
  // dateString is 'YYYY-MM-DD'
  const [year, month, day] = dateString.split('-')
  const date = new Date(Number(year), Number(month) - 1, Number(day))
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function RepeatIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <polyline points="17 1 21 5 17 9" />
      <path d="M3 11V9a4 4 0 0 1 4-4h14" />
      <polyline points="7 23 3 19 7 15" />
      <path d="M21 13v2a4 4 0 0 1-4 4H3" />
    </svg>
  )
}

function ExpenseList({ expenses, onEdit }: ExpenseListProps) {
  if (expenses.length === 0) {
    return (
      <Box py={8} textAlign="center" data-testid="expense-list-empty">
        <Text color="ink.muted">No expenses this month</Text>
      </Box>
    )
  }

  return (
    <Flex direction="column" gap={2} data-testid="expense-list">
      {expenses.map((expense) => {
        const isIncome = expense.entry_type === 'income'
        return (
          <Flex
            key={expense.id}
            align="center"
            p={3}
            borderWidth="1px"
            borderRadius="card"
            borderColor="hairline"
            bg="surface.1"
            gap={3}
            _hover={{ borderColor: 'surface.3', bg: 'surface.2' }}
            transition="border-color 0.15s, background-color 0.15s"
            data-testid={`expense-card-${expense.id}`}
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
              aria-hidden="true"
              data-testid={`expense-category-icon-${expense.id}`}
            >
              {isIncome ? '💵' : (expense.category?.icon ?? '📁')}
            </Flex>

            <Box flex={1} minW={0}>
              <Text
                fontWeight="500"
                color="ink"
                truncate
                data-testid={`expense-category-name-${expense.id}`}
              >
                {isIncome ? 'Income' : (expense.category?.name ?? 'Uncategorized')}
              </Text>
              <Flex gap={1} align="center" color="ink.muted" fontSize="xs" minW={0}>
                <Text flexShrink={0} data-testid={`expense-date-${expense.id}`}>
                  {formatDate(expense.expense_date)}
                </Text>
                {expense.recurring_expense_id && (
                  <Box
                    as="span"
                    flexShrink={0}
                    title="Recurring"
                    aria-label="Recurring"
                    data-testid={`expense-recurring-${expense.id}`}
                  >
                    <RepeatIcon />
                  </Box>
                )}
                {expense.description && (
                  <Text truncate data-testid={`expense-description-${expense.id}`}>
                    · {expense.description}
                  </Text>
                )}
              </Flex>
            </Box>

            <Text
              fontWeight="500"
              fontSize={{ base: 'sm', md: 'md' }}
              color={isIncome ? 'income' : 'spend'}
              fontVariantNumeric="tabular-nums"
              whiteSpace="nowrap"
              flexShrink={0}
              data-testid={`expense-amount-${expense.id}`}
              data-entry-type={expense.entry_type}
            >
              {formatSignedAmount(expense.amount_cents, expense.entry_type)}
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
              onClick={() => onEdit(expense)}
              aria-label={`Edit ${isIncome ? 'income' : 'expense'} ${expense.description || expense.id}`}
              data-testid={`expense-edit-btn-${expense.id}`}
            >
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
            </Button>
          </Flex>
        )
      })}
    </Flex>
  )
}

export default ExpenseList
