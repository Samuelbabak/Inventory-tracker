import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './app/AuthProvider'
import { ProtectedApp } from './app/ProtectedApp'
import { useAuth } from './app/auth'
import { LoginPage } from './features/auth/LoginPage'

function AppRoutes() {
  const { isLoading, user } = useAuth()

  if (isLoading) {
    return (
      <main className="loading-screen" aria-live="polite">
        <span className="loading-mark">H</span>
        <p>Opening warehouse</p>
      </main>
    )
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route
        path="/*"
        element={user ? <ProtectedApp /> : <Navigate to="/login" replace />}
      />
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}
