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
import FAB from '../components/expenses/FAB'
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
    <Container
      maxW="1199px"
      px={{ base: 4, md: 8 }}
      py={{ base: 8, md: 16 }}
      data-testid="expenses-page"
    >
      {/* FAB for quick expense entry */}
      {familyId && <FAB familyId={familyId} />}

      {/* Header */}
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
            Activity
          </Text>
          <Heading
            as="h1"
            fontFamily="heading"
            fontSize={{ base: '52px', md: '85px' }}
            fontWeight="500"
            lineHeight="0.95"
            letterSpacing={{ base: '-2.6px', md: '-4.25px' }}
            color="ink"
          >
            Expenses
          </Heading>
        </Box>
        {familyId && (
          <Button
            colorPalette="brand"
            borderRadius="pill"
            minH="44px"
            px={{ base: 4, md: 5 }}
            _active={{ transform: 'scale(0.97)' }}
            onClick={() => setCreateOpen(true)}
            data-testid="add-expense-btn"
          >
            Add Expense
          </Button>
        )}
      </Flex>

      {/* Month selector */}
      <Flex
        align="center"
        justify="space-between"
        mb={4}
        p={2}
        bg="surface.1"
        borderRadius="pill"
        borderWidth="1px"
        borderColor="hairline"
      >
        <Button
          bg="surface.2"
          color="ink"
          borderRadius="full"
          w="40px"
          h="40px"
          minW="40px"
          onClick={handlePrevMonth}
          aria-label="Previous month"
          _hover={{ bg: 'surface.3' }}
          data-testid="prev-month-btn"
        >
          <PrevIcon />
        </Button>
        <Text
          fontWeight="500"
          fontSize={{ base: 'sm', md: 'md' }}
          fontVariantNumeric="tabular-nums"
          data-testid="month-display"
        >
          {getMonthLabel(yearMonth)}
        </Text>
        <Button
          bg="surface.2"
          color="ink"
          borderRadius="full"
          w="40px"
          h="40px"
          minW="40px"
          onClick={handleNextMonth}
          aria-label="Next month"
          _hover={{ bg: 'surface.3' }}
          data-testid="next-month-btn"
        >
          <NextIcon />
        </Button>
      </Flex>

      {/* Category filter */}
      {familyId && categories.length > 0 && (
        <Box mb={6}>
          <NativeSelectRoot size="sm">
            <NativeSelectField
              bg="surface.1"
              borderColor="hairline"
              borderRadius="10px"
              minH="44px"
              color="ink"
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
          <Text fontSize="sm" color="ink.muted" mb={3} data-testid="expenses-month-label">
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
                bg="surface.1"
                color="ink"
                borderRadius="pill"
                size="sm"
                onClick={() => setPage((p) => p - 1)}
                disabled={page <= 1}
                aria-label="Previous page"
                data-testid="prev-page-btn"
              >
                Previous
              </Button>
              <Text fontSize="sm" color="ink.muted" data-testid="page-indicator">
                Page {page} of {totalPages}
              </Text>
              <Button
                bg="surface.1"
                color="ink"
                borderRadius="pill"
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
