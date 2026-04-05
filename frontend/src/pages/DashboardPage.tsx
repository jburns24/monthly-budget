import { memo, useState } from 'react'
import { Box, Button, Container, Flex, Heading, Spinner, Text } from '@chakra-ui/react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useFamilyContext } from '../contexts/FamilyContext'
import { getBudgetSummary } from '../api/expenses'
import { getGoals } from '../api/goals'
import { getCategories } from '../api/categories'
import type { BudgetCategorySummary } from '../types/expenses'
import type { MonthlyGoal } from '../types/goals'
import { formatCents } from '../utils/format'
import PendingInvites from '../components/family/PendingInvites'
import FAB from '../components/expenses/FAB'
import SetGoalDialog from '../components/goals/SetGoalDialog'
import BulkGoalsEditor from '../components/goals/BulkGoalsEditor'
import RolloverPrompt from '../components/goals/RolloverPrompt'

function getMonthLabel(yearMonth: string): string {
  const [year, month] = yearMonth.split('-')
  const date = new Date(parseInt(year), parseInt(month) - 1, 1)
  return date.toLocaleString('en-US', { month: 'long', year: 'numeric' })
}

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

function getStatusColor(status: string): string {
  switch (status) {
    case 'green':
      return 'accent.500'
    case 'yellow':
      return 'orange.400'
    case 'red':
      return 'red.500'
    default:
      return 'gray.400'
  }
}

interface CategoryCardProps {
  summary: BudgetCategorySummary
  yearMonth: string
  isAdmin: boolean
  existingGoal: MonthlyGoal | undefined
  onClick: (categoryId: string, yearMonth: string) => void
  onGoalClick: (categoryId: string, categoryName: string, goal: MonthlyGoal | undefined) => void
}

const CategoryCard = memo(function CategoryCard({
  summary,
  yearMonth,
  isAdmin,
  existingGoal,
  onClick,
  onGoalClick,
}: CategoryCardProps) {
  const barPercent = summary.goal_cents
    ? Math.min((summary.spent_cents / summary.goal_cents) * 100, 100)
    : 0
  const statusColor = getStatusColor(summary.status)

  function handleGoalButtonClick(e: React.MouseEvent) {
    e.stopPropagation()
    onGoalClick(summary.category_id, summary.category_name, existingGoal)
  }

  return (
    <Box
      p={4}
      borderWidth="1px"
      borderRadius="md"
      borderColor="gray.200"
      cursor="pointer"
      _hover={{ borderColor: 'brand.300', bg: 'gray.50' }}
      transition="border-color 0.15s, background-color 0.15s"
      onClick={() => onClick(summary.category_id, yearMonth)}
      role="button"
      aria-label={`${summary.category_name} category`}
    >
      <Flex align="center" gap={3} mb={2}>
        <Flex
          align="center"
          justify="center"
          w="36px"
          h="36px"
          borderRadius="md"
          bg="brand.50"
          flexShrink={0}
          fontSize="lg"
          aria-hidden="true"
        >
          {summary.icon ?? '📁'}
        </Flex>
        <Box flex={1} minW={0}>
          <Text fontWeight="medium" truncate>
            {summary.category_name}
          </Text>
          <Text fontSize="sm" color="gray.500">
            {formatCents(summary.spent_cents)}
            {summary.goal_cents != null ? ` / ${formatCents(summary.goal_cents)}` : ''}
          </Text>
        </Box>
        <Text fontSize="sm" fontWeight="semibold" color={statusColor} flexShrink={0}>
          {summary.goal_cents != null ? `${Math.round(summary.percentage)}%` : '—'}
        </Text>
      </Flex>

      {/* Progress bar */}
      <Box h="4px" borderRadius="full" bg="gray.100" overflow="hidden">
        {summary.goal_cents != null && (
          <Box
            h="100%"
            borderRadius="full"
            bg={statusColor}
            style={{ width: `${barPercent}%` }}
            transition="width 0.3s ease"
            aria-label={`${Math.round(barPercent)}% of budget used`}
          />
        )}
      </Box>

      {/* Goal button — admin only */}
      {isAdmin && (
        <Flex justify="flex-end" mt={2}>
          <Button
            size="xs"
            variant="ghost"
            colorPalette="brand"
            data-testid={
              existingGoal
                ? `edit-goal-btn-${summary.category_id}`
                : `set-goal-btn-${summary.category_id}`
            }
            onClick={handleGoalButtonClick}
          >
            {existingGoal ? 'Edit Goal \u270F\uFE0F' : 'Set Goal +'}
          </Button>
        </Flex>
      )}
    </Box>
  )
})

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

interface GoalDialogState {
  open: boolean
  categoryId: string
  categoryName: string
  existingGoal: MonthlyGoal | null
}

function DashboardPage() {
  const { familyId, role } = useFamilyContext()
  const navigate = useNavigate()
  const [currentMonth, setCurrentMonth] = useState(getCurrentYearMonth)
  const isAdmin = role === 'admin'

  const [goalDialog, setGoalDialog] = useState<GoalDialogState>({
    open: false,
    categoryId: '',
    categoryName: '',
    existingGoal: null,
  })
  const [bulkEditorOpen, setBulkEditorOpen] = useState(false)

  const {
    data: summary,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['budget-summary', familyId, currentMonth],
    queryFn: () => getBudgetSummary(familyId!, currentMonth),
    enabled: familyId !== null,
    staleTime: 30_000,
  })

  const { data: goalsData } = useQuery({
    queryKey: ['goals', familyId, currentMonth],
    queryFn: () => getGoals(familyId!, currentMonth),
    enabled: familyId !== null,
  })

  const { data: categories } = useQuery({
    queryKey: ['categories', familyId],
    queryFn: () => getCategories(familyId!),
    enabled: familyId !== null && isAdmin,
  })

  function handlePrevMonth() {
    setCurrentMonth((m) => addMonths(m, -1))
  }

  function handleNextMonth() {
    setCurrentMonth((m) => addMonths(m, 1))
  }

  function handleCategoryClick(categoryId: string, yearMonth: string) {
    navigate(`/expenses?category=${categoryId}&month=${yearMonth}`)
  }

  function handleGoalClick(
    categoryId: string,
    categoryName: string,
    existingGoal: MonthlyGoal | undefined
  ) {
    setGoalDialog({
      open: true,
      categoryId,
      categoryName,
      existingGoal: existingGoal ?? null,
    })
  }

  function handleGoalDialogClose() {
    setGoalDialog((prev) => ({ ...prev, open: false }))
  }

  function handleRolloverComplete() {
    // Goals query will be invalidated by RolloverPrompt; nothing extra needed here
  }

  const goals = goalsData?.goals ?? []
  const hasPreviousGoals = goalsData?.has_previous_goals ?? false
  const previousMonth = addMonths(currentMonth, -1)
  const hasNoGoals = goals.length === 0
  const showRolloverPrompt = isAdmin && hasNoGoals && hasPreviousGoals

  const hasExpenses = summary ? summary.categories.some((c) => c.spent_cents > 0) : false

  function getGoalForCategory(categoryId: string): MonthlyGoal | undefined {
    return goals.find((g) => g.category_id === categoryId)
  }

  return (
    <Container maxW="container.md" py={6}>
      {/* FAB for quick expense entry */}
      {familyId && <FAB familyId={familyId} />}

      {/* Month selector */}
      <Flex align="center" justify="space-between" mb={4}>
        <Button
          variant="ghost"
          size="sm"
          onClick={handlePrevMonth}
          aria-label="Previous month"
          px={2}
        >
          <PrevIcon />
        </Button>
        <Heading size="md" textAlign="center">
          {getMonthLabel(currentMonth)}
        </Heading>
        <Button variant="ghost" size="sm" onClick={handleNextMonth} aria-label="Next month" px={2}>
          <NextIcon />
        </Button>
      </Flex>

      {/* No family state */}
      {!familyId && (
        <Box py={12} textAlign="center">
          <PendingInvites />
          <Box mt={6}>
            <Text color="gray.500" mb={4}>
              Create or join a family to start tracking your budget.
            </Text>
            <Button colorPalette="brand" onClick={() => navigate('/family')}>
              Create or join a family
            </Button>
          </Box>
        </Box>
      )}

      {/* Loading state */}
      {familyId && isLoading && (
        <Flex justify="center" py={12}>
          <Spinner size="lg" color="brand.500" aria-label="Loading budget summary" />
        </Flex>
      )}

      {/* Error state */}
      {familyId && isError && (
        <Box py={8} textAlign="center">
          <Text color="red.500">Failed to load budget summary. Please refresh the page.</Text>
        </Box>
      )}

      {/* Rollover prompt — admin only, no goals for month, previous month has goals */}
      {familyId && showRolloverPrompt && (
        <Box mb={4}>
          <RolloverPrompt
            familyId={familyId}
            yearMonth={currentMonth}
            hasPreviousGoals={hasPreviousGoals}
            previousMonth={previousMonth}
            onRolloverComplete={handleRolloverComplete}
          />
        </Box>
      )}

      {/* Budget summary */}
      {summary && (
        <>
          {/* Total spent */}
          <Box
            mb={4}
            p={4}
            borderWidth="1px"
            borderRadius="md"
            borderColor="gray.200"
            bg="brand.50"
          >
            <Text fontSize="sm" color="gray.500">
              Total Spent
            </Text>
            <Text fontSize="2xl" fontWeight="bold" color="brand.500" data-testid="total-spent">
              {formatCents(summary.total_spent_cents)}
            </Text>
          </Box>

          {/* Empty state — has family but no expenses */}
          {!hasExpenses && (
            <Box py={6} textAlign="center">
              <Text color="gray.500" mb={2}>
                No expenses this month.
              </Text>
              <Text fontSize="sm" color="gray.400">
                Add your first expense to start tracking your budget.
              </Text>
            </Box>
          )}

          {/* Category cards — always show all categories */}
          {summary.categories.length > 0 && (
            <Flex direction="column" gap={3}>
              {summary.categories.map((cat) => (
                <CategoryCard
                  key={cat.category_id}
                  summary={cat}
                  yearMonth={currentMonth}
                  isAdmin={isAdmin}
                  existingGoal={getGoalForCategory(cat.category_id)}
                  onClick={handleCategoryClick}
                  onGoalClick={handleGoalClick}
                />
              ))}
            </Flex>
          )}

          {/* Manage All Goals button — admin only */}
          {isAdmin && summary.categories.length > 0 && (
            <Flex justify="flex-start" mt={4}>
              <Button
                variant="outline"
                size="sm"
                colorPalette="brand"
                data-testid="manage-goals-btn"
                onClick={() => setBulkEditorOpen(true)}
              >
                Manage All Goals
              </Button>
            </Flex>
          )}
        </>
      )}

      {/* SetGoalDialog */}
      {familyId && goalDialog.open && (
        <SetGoalDialog
          open={goalDialog.open}
          onOpenChange={(open) => !open && handleGoalDialogClose()}
          familyId={familyId}
          yearMonth={currentMonth}
          categoryId={goalDialog.categoryId}
          categoryName={goalDialog.categoryName}
          existingGoal={goalDialog.existingGoal}
        />
      )}

      {/* BulkGoalsEditor */}
      {familyId && isAdmin && (
        <BulkGoalsEditor
          isOpen={bulkEditorOpen}
          onClose={() => setBulkEditorOpen(false)}
          familyId={familyId}
          yearMonth={currentMonth}
          categories={categories ?? []}
          currentGoals={goals}
        />
      )}
    </Container>
  )
}

export default DashboardPage
