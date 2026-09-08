import { createContext, useContext, useMemo } from 'react'
import { useAuth } from './AuthContext'

const PermissionContext = createContext(null)

export function PermissionProvider({ children }) {
  const { user } = useAuth()
  const permissions = useMemo(() => new Set(user?.permissions || []), [user?.permissions])
  const can = (permission) => permissions.has(permission) || permissions.has('*')
  const canAny = (items = []) => items.some(can)
  const canAll = (items = []) => items.every(can)
  return <PermissionContext.Provider value={{ can, canAny, canAll, permissions }}>{children}</PermissionContext.Provider>
}

export const usePermissions = () => useContext(PermissionContext)
