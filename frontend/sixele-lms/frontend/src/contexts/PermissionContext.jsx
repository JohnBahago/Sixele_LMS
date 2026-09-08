import { createContext, useContext } from 'react'
import { useAuth } from './AuthContext'
const PermissionContext = createContext(null)
export function PermissionProvider({ children }) {
  const { user } = useAuth()
  const can = (permission) => !!user?.permissions?.includes(permission)
  const canAny = (permissions) => permissions.some(can)
  const canAll = (permissions) => permissions.every(can)
  return <PermissionContext.Provider value={{can, canAny, canAll}}>{children}</PermissionContext.Provider>
}
export const usePermissions = () => useContext(PermissionContext)
