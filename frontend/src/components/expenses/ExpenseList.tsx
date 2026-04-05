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
              Edit
            </Button>
            <Button
              size="xs"
              variant="ghost"
              colorPalette="red"
              onClick={() => onDelete(expense)}
              aria-label={`Delete expense ${expense.description || expense.id}`}
              data-testid={`expense-delete-btn-${expense.id}`}
            >
              Delete
            </Button>
          </Flex>
        </Flex>
      ))}
    </Flex>
  )
}

export default ExpenseList
