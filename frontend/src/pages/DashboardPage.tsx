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
      return 'white'
    case 'yellow':
      return 'gradient.orange'
    case 'red':
      return 'gradient.coral'
    default:
      return 'ink.muted'
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
      p={{ base: 4, md: 5 }}
      borderWidth="1px"
      borderRadius="card"
      borderColor="hairline"
      bg="surface.1"
      cursor="pointer"
      _hover={{
        borderColor: 'surface.3',
        bg: 'surface.2',
        transform: 'translateY(-2px)',
      }}
      _active={{ transform: 'scale(0.99)' }}
      transition="border-color 0.15s, background-color 0.15s, transform 0.15s"
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
          borderRadius="10px"
          bg="surface.2"
          borderWidth="1px"
          borderColor="hairline"
          flexShrink={0}
          fontSize="lg"
          aria-hidden="true"
        >
          {summary.icon ?? '📁'}
        </Flex>
        <Box flex={1} minW={0}>
          <Text fontWeight="500" color="ink" letterSpacing="-0.15px" truncate>
            {summary.category_name}
          </Text>
          <Text fontSize="sm" color="ink.muted" fontVariantNumeric="tabular-nums">
            {formatCents(summary.spent_cents)}
            {summary.goal_cents != null ? ` / ${formatCents(summary.goal_cents)}` : ''}
          </Text>
        </Box>
      </Flex>

      {/* Progress bar */}
      <Box h="4px" borderRadius="full" bg="surface.3" overflow="hidden">
        {summary.goal_cents != null && (
          <Box
            h="100%"
            borderRadius="full"
            bg={statusColor}
            style={{ width: `${barPercent}%` }}
            transition="width 0.3s ease"
            role="progressbar"
            aria-label={`${Math.round(barPercent)}% of budget used`}
            aria-valuenow={Math.round(barPercent)}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        )}
      </Box>

      {/* Goal button — admin only */}
      {isAdmin && (
        <Flex justify="flex-end" mt={2}>
          <Button
            size="xs"
            bg="surface.2"
            color="ink"
            borderRadius="pill"
            px={3}
            _hover={{ bg: 'surface.3' }}
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
    <Container maxW="1199px" px={{ base: 4, md: 8 }} py={{ base: 8, md: 16 }}>
      {/* FAB for quick expense entry */}
      {familyId && <FAB familyId={familyId} />}

      {/* Month selector */}
      <Box mb={{ base: 8, md: 12 }}>
        <Text
          color="ink.muted"
          fontSize="caption"
          fontWeight="500"
          textTransform="uppercase"
          letterSpacing="0.08em"
          mb={3}
        >
          Monthly overview
        </Text>
        <Flex align="center" gap={{ base: 2, md: 4 }}>
          <Button
            bg="surface.1"
            color="ink"
            borderRadius="full"
            w={{ base: '44px', md: '48px' }}
            h={{ base: '44px', md: '48px' }}
            minW={{ base: '44px', md: '48px' }}
            onClick={handlePrevMonth}
            aria-label="Previous month"
            _hover={{ bg: 'surface.2' }}
            _active={{ transform: 'scale(0.95)' }}
          >
            <PrevIcon />
          </Button>
          <Heading
            as="h1"
            flex={1}
            fontFamily="heading"
            fontSize={{ base: '42px', md: '72px', lg: '85px' }}
            fontWeight="500"
            lineHeight="0.95"
            letterSpacing={{ base: '-2.1px', md: '-3.6px', lg: '-4.25px' }}
            color="ink"
            textAlign="center"
          >
            {getMonthLabel(currentMonth)}
          </Heading>
          <Button
            bg="surface.1"
            color="ink"
            borderRadius="full"
            w={{ base: '44px', md: '48px' }}
            h={{ base: '44px', md: '48px' }}
            minW={{ base: '44px', md: '48px' }}
            onClick={handleNextMonth}
            aria-label="Next month"
            _hover={{ bg: 'surface.2' }}
            _active={{ transform: 'scale(0.95)' }}
          >
            <NextIcon />
          </Button>
        </Flex>
      </Box>

      {/* No family state */}
      {!familyId && (
        <Box py={12} textAlign="center">
          <PendingInvites />
          <Box mt={6}>
            <Text color="gray.500" mb={4}>
              Create or join a family to start tracking your budget.
            </Text>
            <Button
              colorPalette="brand"
              borderRadius="pill"
              minH="44px"
              px={5}
              onClick={() => navigate('/family')}
            >
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
            position="relative"
            overflow="hidden"
            mb={{ base: 6, md: 8 }}
            p={{ base: 6, md: 8 }}
            minH={{ base: '190px', md: '250px' }}
            borderRadius="spotlight"
            bg="gradient.violet"
            background="radial-gradient(circle at 82% 18%, rgba(255,255,255,0.34), transparent 24%), radial-gradient(circle at 14% 92%, #d44bd3 0, transparent 42%), linear-gradient(135deg, #352073 0%, #7046d9 55%, #a34ec9 100%)"
            display="flex"
            flexDirection="column"
            justifyContent="space-between"
            boxShadow="inset 0 1px 0 rgba(255,255,255,0.18), 0 24px 60px rgba(51, 28, 110, 0.28)"
          >
            <Text fontSize="sm" color="rgba(255,255,255,0.72)" fontWeight="500">
              Total Spent
            </Text>
            <Text
              fontFamily="heading"
              fontSize={{ base: '52px', md: '76px' }}
              lineHeight="0.95"
              letterSpacing={{ base: '-2.6px', md: '-3.8px' }}
              fontWeight="500"
              color="white"
              fontVariantNumeric="tabular-nums"
              data-testid="total-spent"
            >
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
            <Box
              display="grid"
              gridTemplateColumns={{ base: '1fr', md: 'repeat(2, minmax(0, 1fr))' }}
              gap={3}
            >
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
            </Box>
          )}

          {/* Manage All Goals button — admin only */}
          {isAdmin && summary.categories.length > 0 && (
            <Flex justify="flex-start" mt={5}>
              <Button
                bg="surface.1"
                color="ink"
                size="sm"
                borderRadius="pill"
                minH="44px"
                px={5}
                _hover={{ bg: 'surface.2' }}
                data-testid="manage-goals-btn"
                onClick={() => setBulkEditorOpen(true)}
              >
                Manage All Goals
              </Button>
            </Flex>
          )}
        </>
      )}

      {/* SetGoalDialog — always mounted so closing does not unmount mid-refetch */}
      {familyId && (
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
