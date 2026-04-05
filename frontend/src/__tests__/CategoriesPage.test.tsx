import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ChakraProvider } from '@chakra-ui/react'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import CategoriesPage from '../pages/CategoriesPage'
import { FamilyProvider } from '../contexts/FamilyContext'
import system from '../theme'

// Mock useAuth to control auth + family state
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(),
}))

// Mock categories API to prevent real HTTP calls
vi.mock('../api/categories', () => ({
  getCategories: vi.fn(() => new Promise(() => {})),
  createCategory: vi.fn(() => new Promise(() => {})),
  updateCategory: vi.fn(() => new Promise(() => {})),
  deleteCategory: vi.fn(() => new Promise(() => {})),
  seedCategories: vi.fn(() => new Promise(() => {})),
}))

import { useAuth } from '../hooks/useAuth'
import { getCategories } from '../api/categories'

const FAMILY_ID = 'fam-123'

function makeAdminUser() {
  return {
    id: 'user-1',
    email: 'admin@example.com',
    display_name: 'Admin User',
    avatar_url: null,
    timezone: 'UTC',
    family: { id: FAMILY_ID, name: 'Test Family', role: 'admin' as const },
  }
}

function makeMemberUser() {
  return {
    id: 'user-2',
    email: 'member@example.com',
    display_name: 'Member User',
    avatar_url: null,
    timezone: 'UTC',
    family: { id: FAMILY_ID, name: 'Test Family', role: 'member' as const },
  }
}

function renderCategoriesPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={['/categories']}>
      <ChakraProvider value={system}>
        <QueryClientProvider client={queryClient}>
          <FamilyProvider>
            <Routes>
              <Route path="/categories" element={<CategoriesPage />} />
            </Routes>
          </FamilyProvider>
        </QueryClientProvider>
      </ChakraProvider>
    </MemoryRouter>
  )
}

const sampleCategories = [
  {
    id: 'cat-1',
    family_id: FAMILY_ID,
    name: 'Groceries',
    icon: '🛒',
    sort_order: 1,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'cat-2',
    family_id: FAMILY_ID,
    name: 'Transport',
    icon: '🚗',
    sort_order: 2,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
  },
]

describe('CategoriesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders spinner when query is pending', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    // getCategories returns a never-resolving promise by default (from module mock)

    renderCategoriesPage()

    expect(screen.getByLabelText('Loading categories')).toBeInTheDocument()
  })

  it('renders categories in list when data is available', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCategoriesPage()

    await waitFor(() => {
      expect(screen.getByText('Groceries')).toBeInTheDocument()
      expect(screen.getByText('Transport')).toBeInTheDocument()
    })
  })

  it('admin sees Add Category, Edit, and Delete buttons', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCategoriesPage()

    // Wait for categories to load
    await waitFor(() => {
      expect(screen.getByText('Groceries')).toBeInTheDocument()
    })

    expect(screen.getByRole('button', { name: /add category/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /edit groceries/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /delete groceries/i })).toBeInTheDocument()
  })

  it('member does not see Add, Edit, or Delete buttons', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeMemberUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCategoriesPage()

    await waitFor(() => {
      expect(screen.getByText('Groceries')).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: /add category/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /edit groceries/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /delete groceries/i })).not.toBeInTheDocument()
  })

  it('create dialog opens when Add Category button is clicked (admin)', async () => {
    const user = userEvent.setup()
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue(sampleCategories)

    renderCategoriesPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add category/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /add category/i }))

    // Dialog or modal should appear
    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })
  })

  it('empty state shows Seed defaults button for admin', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue([])

    renderCategoriesPage()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /seed defaults/i })).toBeInTheDocument()
    })
  })

  it('empty state does NOT show seed button for member', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeMemberUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockResolvedValue([])

    renderCategoriesPage()

    await waitFor(() => {
      // Empty state text shows for members
      expect(screen.getByText(/no categories yet/i)).toBeInTheDocument()
    })

    expect(screen.queryByRole('button', { name: /seed defaults/i })).not.toBeInTheDocument()
  })

  it('shows error message when query fails', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: makeAdminUser(),
      isLoading: false,
      isAuthenticated: true,
      logout: vi.fn().mockResolvedValue(undefined),
    })
    vi.mocked(getCategories).mockRejectedValue(new Error('Network error'))

    renderCategoriesPage()

    await waitFor(() => {
      expect(screen.getByText(/failed to load categories/i)).toBeInTheDocument()
    })
  })
})
