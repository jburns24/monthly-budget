import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect } from 'vitest'
import ExpenseList from '../components/expenses/ExpenseList'
import type { Expense } from '../types/expenses'
import system from '../theme'

function renderExpenseList(expenses: Expense[], onEdit = vi.fn(), onDelete = vi.fn()) {
  return render(
    <ChakraProvider value={system}>
      <ExpenseList expenses={expenses} onEdit={onEdit} onDelete={onDelete} />
    </ChakraProvider>
  )
}

const sampleExpenses: Expense[] = [
  {
    id: 'exp-1',
    family_id: 'fam-1',
    category: { id: 'cat-1', name: 'Groceries', icon: '🛒' },
    created_by_user: { id: 'user-1', display_name: 'Alice' },
    amount_cents: 4523,
    description: 'Weekly groceries',
    expense_date: '2026-04-01',
    created_at: '2026-04-01T10:00:00Z',
    updated_at: '2026-04-01T10:00:00Z',
  },
  {
    id: 'exp-2',
    family_id: 'fam-1',
    category: { id: 'cat-2', name: 'Transport', icon: '🚗' },
    created_by_user: { id: 'user-2', display_name: 'Bob' },
    amount_cents: 1500,
    description: 'Bus pass',
    expense_date: '2026-04-03',
    created_at: '2026-04-03T08:00:00Z',
    updated_at: '2026-04-03T08:00:00Z',
  },
]

describe('ExpenseList', () => {
  it('renders empty state when no expenses', () => {
    renderExpenseList([])

    expect(screen.getByTestId('expense-list-empty')).toBeInTheDocument()
    expect(screen.getByText('No expenses this month')).toBeInTheDocument()
  })

  it('does not render the empty state when expenses exist', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.queryByTestId('expense-list-empty')).not.toBeInTheDocument()
  })

  it('renders a card for each expense', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-card-exp-1')).toBeInTheDocument()
    expect(screen.getByTestId('expense-card-exp-2')).toBeInTheDocument()
  })

  it('shows formatted amount (cents to dollars)', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-amount-exp-1')).toHaveTextContent('$45.23')
    expect(screen.getByTestId('expense-amount-exp-2')).toHaveTextContent('$15.00')
  })

  it('shows expense description', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-description-exp-1')).toHaveTextContent('Weekly groceries')
    expect(screen.getByTestId('expense-description-exp-2')).toHaveTextContent('Bus pass')
  })

  it('shows category name on each card', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-category-name-exp-1')).toHaveTextContent('Groceries')
    expect(screen.getByTestId('expense-category-name-exp-2')).toHaveTextContent('Transport')
  })

  it('shows category icon on each card', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-category-icon-exp-1')).toHaveTextContent('🛒')
    expect(screen.getByTestId('expense-category-icon-exp-2')).toHaveTextContent('🚗')
  })

  it('shows user display name on each card', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-user-exp-1')).toHaveTextContent('Alice')
    expect(screen.getByTestId('expense-user-exp-2')).toHaveTextContent('Bob')
  })

  it('shows expense date on each card', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-date-exp-1')).toBeInTheDocument()
    expect(screen.getByTestId('expense-date-exp-2')).toBeInTheDocument()
  })

  it('renders edit and delete buttons on each card', () => {
    renderExpenseList(sampleExpenses)

    expect(screen.getByTestId('expense-edit-btn-exp-1')).toBeInTheDocument()
    expect(screen.getByTestId('expense-delete-btn-exp-1')).toBeInTheDocument()
    expect(screen.getByTestId('expense-edit-btn-exp-2')).toBeInTheDocument()
    expect(screen.getByTestId('expense-delete-btn-exp-2')).toBeInTheDocument()
  })

  it('calls onEdit with the correct expense when edit is clicked', async () => {
    const user = userEvent.setup()
    const onEdit = vi.fn()
    renderExpenseList(sampleExpenses, onEdit)

    await user.click(screen.getByTestId('expense-edit-btn-exp-1'))

    expect(onEdit).toHaveBeenCalledTimes(1)
    expect(onEdit).toHaveBeenCalledWith(sampleExpenses[0])
  })

  it('calls onDelete with the correct expense when delete is clicked', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    renderExpenseList(sampleExpenses, vi.fn(), onDelete)

    await user.click(screen.getByTestId('expense-delete-btn-exp-2'))

    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onDelete).toHaveBeenCalledWith(sampleExpenses[1])
  })

  it('shows fallback icon when category has no icon', () => {
    const expenseWithNoIcon: Expense[] = [
      {
        ...sampleExpenses[0],
        id: 'exp-no-icon',
        category: { id: 'cat-3', name: 'Other', icon: null },
      },
    ]
    renderExpenseList(expenseWithNoIcon)

    expect(screen.getByTestId('expense-category-icon-exp-no-icon')).toHaveTextContent('📁')
  })

  it('shows fallback description text when description is empty', () => {
    const expenseNoDesc: Expense[] = [
      {
        ...sampleExpenses[0],
        id: 'exp-no-desc',
        description: '',
      },
    ]
    renderExpenseList(expenseNoDesc)

    expect(screen.getByTestId('expense-description-exp-no-desc')).toHaveTextContent(
      '(no description)'
    )
  })
})
