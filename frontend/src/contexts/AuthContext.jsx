import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'

const AuthContext = createContext(null)

const normalizeUser = (user) => user ? ({
  ...user,
  name: user.full_name || user.name || 'Sixele User',
  roles: user.roles || [],
  permissions: Array.isArray(user.permissions) ? user.permissions : [],
}) : null

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const token = localStorage.getItem('sixele.access_token')
    if (!token) { setLoading(false); return }
    api.me().then(data => setUser(normalizeUser(data))).catch(() => {
      localStorage.removeItem('sixele.access_token')
      setUser(null)
    }).finally(() => setLoading(false))
  }, [])

  const login = async (email, password) => {
    setError('')
    const data = await api.login(email, password)
    localStorage.setItem('sixele.access_token', data.access_token)
    setUser(normalizeUser(data.user))
    return data.user
  }

  const register = async (fullName, email, password) => {
    setError('')
    const data = await api.register(fullName, email, password)
    localStorage.setItem('sixele.access_token', data.access_token)
    setUser(normalizeUser(data.user))
    return data.user
  }

  const logout = () => {
    localStorage.removeItem('sixele.access_token')
    setUser(null)
  }

  const refreshUser = async () => {
    const data = await api.me()
    const normalized = normalizeUser(data)
    setUser(normalized)
    return normalized
  }

  const value = useMemo(() => ({ user, loading, error, setError, login, register, logout, refreshUser, isAuthenticated: !!user }), [user, loading, error])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
