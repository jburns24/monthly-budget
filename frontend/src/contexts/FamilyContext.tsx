import { createContext, useContext } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '../hooks/useAuth'
import type { FamilyBrief } from '../types/family'

interface FamilyContextValue {
  familyId: string | null
  role: FamilyBrief['role'] | null
  family: FamilyBrief | null
}

const FamilyContext = createContext<FamilyContextValue>({
  familyId: null,
  role: null,
  family: null,
})

interface FamilyProviderProps {
  children: ReactNode
}

export function FamilyProvider({ children }: FamilyProviderProps) {
  const { user } = useAuth()

  const value: FamilyContextValue = {
    familyId: user?.family?.id ?? null,
    role: user?.family?.role ?? null,
    family: user?.family ?? null,
  }

  return <FamilyContext.Provider value={value}>{children}</FamilyContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useFamilyContext(): FamilyContextValue {
  return useContext(FamilyContext)
}
