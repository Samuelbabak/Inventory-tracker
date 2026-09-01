import { createContext, use } from 'react'
import type { UserContext } from '../api/types'

export interface AuthState {
  user: UserContext | null
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const value = use(AuthContext)
  if (!value) throw new Error('useAuth must be used within AuthProvider')
  return value
}
