import { useState } from 'react'
import {
  Box,
  Button,
  Container,
  Flex,
  Heading,
  NativeSelectField,
  NativeSelectRoot,
  Spinner,
  Text,
} from '@chakra-ui/react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { useFamilyContext } from '../contexts/FamilyContext'
import { getExpenses } from '../api/expenses'
import { getCategories } from '../api/categories'
import ExpenseList from '../components/expenses/ExpenseList'
import CreateExpenseDialog from '../components/expenses/CreateExpenseDialog'
import EditExpenseDialog from '../components/expenses/EditExpenseDialog'
import DeleteExpenseDialog from '../components/expenses/DeleteExpenseDialog'
import type { Expense } from '../types/expenses'

const PER_PAGE = 20

function getCurrentYearMonth(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

function addMonths(yearMonth: string, delta: number): string {
  const [year, month] = yearMonth.split('-').map(Number)
  const date = new Date(year, month - 1 + delta, 1)
  const newYear = date.getFullYear()
  const newMonth = String(date.getMonth() + 1).padStart(2, '0')
  return `${newYear}-${newMonth}`
}

function getMonthLabel(yearMonth: string): string {
  const [year, month] = yearMonth.split('-')
  const date = new Date(parseInt(year), parseInt(month) - 1, 1)
  return date.toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

function PrevIcon() {
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
      <polyline points="15 18 9 12 15 6" />
    </svg>
  )
}

function NextIcon() {
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
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}

function ExpensesPage() {
  const { familyId } = useFamilyContext()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()

  // Initialize from URL search params (e.g. from DashboardPage category click)
  const initialMonth = searchParams.get('month') ?? getCurrentYearMonth()
  const initialCategoryId = searchParams.get('category') ?? ''

  const [yearMonth, setYearMonth] = useState(initialMonth)
  const [categoryId, setCategoryId] = useState(initialCategoryId)
  const [page, setPage] = useState(1)

  const [createOpen, setCreateOpen] = useState(false)
  const [editExpense, setEditExpense] = useState<Expense | null>(null)
  const [deleteExpense, setDeleteExpense] = useState<Expense | null>(null)

  const { data: categories = [] } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId!),
    enabled: familyId !== null,
  })

  const {
    data: expenseData,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['expenses', familyId, yearMonth, categoryId || undefined, page],
    queryFn: () => getExpenses(familyId!, yearMonth, categoryId || undefined, page, PER_PAGE),
    enabled: familyId !== null,
  })

  function handlePrevMonth() {
    setYearMonth((m) => addMonths(m, -1))
    setPage(1)
  }

  function handleNextMonth() {
    setYearMonth((m) => addMonths(m, 1))
    setPage(1)
  }

  function handleCategoryChange(newCategoryId: string) {
    setCategoryId(newCategoryId)
    setPage(1)
  }

  function handleExpenseChanged() {
    queryClient.invalidateQueries({ queryKey: ['expenses', familyId] })
    queryClient.invalidateQueries({ queryKey: ['budget-summary', familyId] })
  }

  const totalCount = expenseData?.total_count ?? 0
  const totalPages = Math.ceil(totalCount / PER_PAGE)
  const showPagination = totalCount > PER_PAGE

  return (
    <Container maxW="container.md" py={6} data-testid="expenses-page">
      {/* FAB for quick expense entry */}
      {familyId && (
        <Box
          as="button"
          position="fixed"
          bottom="80px"
          right="16px"
          zIndex="overlay"
          w="56px"
          h="56px"
          minW="48px"
          minH="48px"
          borderRadius="full"
          bg="brand.500"
          color="white"
          display="flex"
          alignItems="center"
          justifyContent="center"
          boxShadow="lg"
          cursor="pointer"
          transition="background-color 0.15s, box-shadow 0.15s, transform 0.1s"
          _hover={{ bg: 'brand.600', boxShadow: 'xl' }}
          _active={{ bg: 'brand.700', transform: 'scale(0.95)' }}
          _focusVisible={{
            outline: '2px solid',
            outlineColor: 'brand.500',
            outlineOffset: '2px',
          }}
          onClick={() => setCreateOpen(true)}
          aria-label="Add expense"
          data-testid="fab-add-expense"
        >
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </Box>
      )}

      {/* Header */}
      <Flex align="center" justify="space-between" mb={4}>
        <Heading size="lg">Expenses</Heading>
        {familyId && (
          <Button
            colorPalette="brand"
            size="sm"
            onClick={() => setCreateOpen(true)}
            data-testid="add-expense-btn"
          >
            Add Expense
          </Button>
        )}
      </Flex>

      {/* Month selector */}
      <Flex align="center" justify="space-between" mb={4}>
        <Button
          variant="ghost"
          size="sm"
          onClick={handlePrevMonth}
          aria-label="Previous month"
          px={2}
          data-testid="prev-month-btn"
        >
          <PrevIcon />
        </Button>
        <Text fontWeight="semibold" data-testid="month-display">
          {yearMonth}
        </Text>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleNextMonth}
          aria-label="Next month"
          px={2}
          data-testid="next-month-btn"
        >
          <NextIcon />
        </Button>
      </Flex>

      {/* Category filter */}
      {familyId && categories.length > 0 && (
        <Box mb={4}>
          <NativeSelectRoot size="sm">
            <NativeSelectField
              value={categoryId}
              onChange={(e) => handleCategoryChange(e.target.value)}
              aria-label="Filter by category"
              data-testid="category-filter-select"
            >
              <option value="">All Categories</option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.icon ? `${cat.icon} ` : ''}
                  {cat.name}
                </option>
              ))}
            </NativeSelectField>
          </NativeSelectRoot>
        </Box>
      )}

      {/* No family state */}
      {!familyId && (
        <Box py={12} textAlign="center">
          <Text color="gray.500">Create or join a family to track expenses.</Text>
        </Box>
      )}

      {/* Loading state */}
      {familyId && isLoading && (
        <Flex justify="center" py={12}>
          <Spinner size="lg" color="brand.500" aria-label="Loading expenses" />
        </Flex>
      )}

      {/* Error state */}
      {familyId && isError && (
        <Box py={8} textAlign="center">
          <Text color="red.500">Failed to load expenses. Please refresh the page.</Text>
        </Box>
      )}

      {/* Expense list */}
      {familyId && expenseData && (
        <>
          <Text fontSize="sm" color="gray.500" mb={3} data-testid="expenses-month-label">
            {getMonthLabel(yearMonth)}
            {totalCount > 0 && ` — ${totalCount} expense${totalCount !== 1 ? 's' : ''}`}
          </Text>
          <ExpenseList
            expenses={expenseData.expenses}
            onEdit={(expense) => setEditExpense(expense)}
            onDelete={(expense) => setDeleteExpense(expense)}
          />

          {/* Pagination */}
          {showPagination && (
            <Flex justify="center" align="center" gap={4} mt={6} data-testid="pagination-controls">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p - 1)}
                disabled={page <= 1}
                aria-label="Previous page"
                data-testid="prev-page-btn"
              >
                Previous
              </Button>
              <Text fontSize="sm" color="gray.600" data-testid="page-indicator">
                Page {page} of {totalPages}
              </Text>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= totalPages}
                aria-label="Next page"
                data-testid="next-page-btn"
              >
                Next
              </Button>
            </Flex>
          )}
        </>
      )}

      {/* Dialogs */}
      {familyId && (
        <>
          <CreateExpenseDialog
            open={createOpen}
            onOpenChange={(open) => {
              setCreateOpen(open)
              if (!open) handleExpenseChanged()
            }}
            familyId={familyId}
          />
          <EditExpenseDialog
            open={editExpense !== null}
            onOpenChange={(open) => {
              if (!open) {
                setEditExpense(null)
                handleExpenseChanged()
              }
            }}
            familyId={familyId}
            expense={editExpense}
          />
          <DeleteExpenseDialog
            open={deleteExpense !== null}
            onOpenChange={(open) => {
              if (!open) {
                setDeleteExpense(null)
                handleExpenseChanged()
              }
            }}
            familyId={familyId}
            expense={deleteExpense}
          />
        </>
      )}
    </Container>
  )
}

export default ExpensesPage
