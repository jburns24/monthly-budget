import { useQuery, useQueryClient } from '@tanstack/react-query'

export interface User {
  id: string
  email: string
  display_name: string
  avatar_url: string | null
  timezone: string
}

async function fetchCurrentUser(): Promise<User | null> {
  const response = await fetch('/api/me')
  if (response.status === 401) {
    return null
  }
  if (!response.ok) {
    throw new Error(`Failed to fetch user: ${response.status}`)
  }
  return response.json() as Promise<User>
}

export function useAuth() {
  const queryClient = useQueryClient()

  const { data: user = null, isLoading } = useQuery<User | null>({
    queryKey: ['currentUser'],
    queryFn: fetchCurrentUser,
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const logout = async (): Promise<void> => {
    await fetch('/api/auth/logout', { method: 'POST' })
    queryClient.clear()
  }

  return {
    user,
    isLoading,
    isAuthenticated: user !== null,
    logout,
  }
}
