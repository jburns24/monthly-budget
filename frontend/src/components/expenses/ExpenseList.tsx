import { Box, Button, Flex, Text } from '@chakra-ui/react'
import type { Expense } from '../../types/expenses'

interface ExpenseListProps {
  expenses: Expense[]
  onEdit: (expense: Expense) => void
  onDelete: (expense: Expense) => void
}

function formatAmount(amountCents: number): string {
  return `$${(amountCents / 100).toFixed(2)}`
}

function formatDate(dateString: string): string {
  // dateString is 'YYYY-MM-DD'
  const [year, month, day] = dateString.split('-')
  const date = new Date(Number(year), Number(month) - 1, Number(day))
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function ExpenseList({ expenses, onEdit, onDelete }: ExpenseListProps) {
  if (expenses.length === 0) {
    return (
      <Box py={8} textAlign="center" data-testid="expense-list-empty">
        <Text color="gray.500">No expenses this month</Text>
      </Box>
    )
  }

  return (
    <Flex direction="column" gap={3} data-testid="expense-list">
      {expenses.map((expense) => (
        <Flex
          key={expense.id}
          align="center"
          p={4}
          borderWidth="1px"
          borderRadius="md"
          borderColor="gray.200"
          gap={3}
          _hover={{ borderColor: 'brand.300', bg: 'gray.50' }}
          transition="border-color 0.15s, background-color 0.15s"
          data-testid={`expense-card-${expense.id}`}
        >
          {/* Category icon */}
          <Flex
            align="center"
            justify="center"
            w="40px"
            h="40px"
            borderRadius="md"
            bg="brand.50"
            flexShrink={0}
            fontSize="xl"
            aria-hidden="true"
            data-testid={`expense-category-icon-${expense.id}`}
          >
            {expense.category.icon ?? '📁'}
          </Flex>

          {/* Description and meta */}
          <Box flex={1} minW={0}>
            <Text fontWeight="medium" truncate data-testid={`expense-description-${expense.id}`}>
              {expense.description || '(no description)'}
            </Text>
            <Flex gap={2} align="center" flexWrap="wrap">
              <Text
                fontSize="xs"
                color="gray.500"
                data-testid={`expense-category-name-${expense.id}`}
              >
                {expense.category.icon ? `${expense.category.icon} ` : ''}
                {expense.category.name}
              </Text>
              <Text fontSize="xs" color="gray.400" aria-hidden="true">
                ·
              </Text>
              <Text fontSize="xs" color="gray.500" data-testid={`expense-user-${expense.id}`}>
                {expense.created_by_user.display_name}
              </Text>
              <Text fontSize="xs" color="gray.400" aria-hidden="true">
                ·
              </Text>
              <Text fontSize="xs" color="gray.500" data-testid={`expense-date-${expense.id}`}>
                {formatDate(expense.expense_date)}
              </Text>
            </Flex>
          </Box>

          {/* Amount */}
          <Text
            fontWeight="semibold"
            fontSize="md"
            color="gray.800"
            flexShrink={0}
            data-testid={`expense-amount-${expense.id}`}
          >
            {formatAmount(expense.amount_cents)}
          </Text>

          {/* Edit and delete controls */}
          <Flex gap={2} flexShrink={0}>
            <Button
              size="xs"
              variant="ghost"
              colorPalette="brand"
              onClick={() => onEdit(expense)}
              aria-label={`Edit expense ${expense.description || expense.id}`}
              data-testid={`expense-edit-btn-${expense.id}`}
            >
              <svg
                width="14"
                height="14"
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
            <Button
              size="xs"
              variant="ghost"
              colorPalette="red"
              onClick={() => onDelete(expense)}
              aria-label={`Delete expense ${expense.description || expense.id}`}
              data-testid={`expense-delete-btn-${expense.id}`}
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                <path d="M10 11v6" />
                <path d="M14 11v6" />
                <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
              </svg>
            </Button>
          </Flex>
        </Flex>
      ))}
    </Flex>
  )
}

export default ExpenseList
