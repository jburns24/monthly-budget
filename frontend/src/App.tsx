import { Box } from '@chakra-ui/react'
import { Routes, Route } from 'react-router-dom'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import AuthCallbackPage from './pages/AuthCallbackPage'
import FamilyPage from './pages/FamilyPage'
import CategoriesPage from './pages/CategoriesPage'
import { ProtectedRoute } from './components/ProtectedRoute'
import Header from './components/Header'
import BottomNavigation from './components/BottomNavigation'
import { FamilyProvider } from './contexts/FamilyContext'

function ProtectedLayout({ children }: { children: React.ReactNode }) {
  return (
    <FamilyProvider>
      <Box pb="64px">{children}</Box>
      <BottomNavigation />
    </FamilyProvider>
  )
}

function App() {
  return (
    <>
      <Header />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <ProtectedLayout>
                <DashboardPage />
              </ProtectedLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/family"
          element={
            <ProtectedRoute>
              <ProtectedLayout>
                <FamilyPage />
              </ProtectedLayout>
            </ProtectedRoute>
          }
        />
        <Route
          path="/categories"
          element={
            <ProtectedRoute>
              <ProtectedLayout>
                <CategoriesPage />
              </ProtectedLayout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </>
  )
}

export default App
