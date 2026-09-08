import { createContext, useContext, useState } from 'react'
import { mockUser } from '../data/mockData'
const AuthContext = createContext(null)
export function AuthProvider({ children }) {
  const [user, setUser] = useState(mockUser)
  const login = () => setUser(mockUser)
  const logout = () => setUser(null)
  return <AuthContext.Provider value={{user, login, logout}}>{children}</AuthContext.Provider>
}
export const useAuth = () => useContext(AuthContext)
