import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { UserContext } from '../api/types'
import { AuthContext, type AuthState } from './auth'

export function AuthProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [user, setUser] = useState<UserContext | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let active = true
    api
      .me()
      .then((currentUser) => {
        if (active) setUser(currentUser)
      })
      .catch(() => {
        if (active) setUser(null)
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  const value = useMemo<AuthState>(
    () => ({
      user,
      isLoading,
      login: async (username: string, password: string) => {
        setUser(await api.login(username, password))
      },
      logout: async () => {
        await api.logout()
        setUser(null)
      },
    }),
    [isLoading, user],
  )

  return <AuthContext value={value}>{children}</AuthContext>
}
