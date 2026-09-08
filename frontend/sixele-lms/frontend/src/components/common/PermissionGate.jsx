import { usePermissions } from '../../contexts/PermissionContext'
export default function PermissionGate({ permission, anyOf, children, fallback=null }) {
  const { can, canAny } = usePermissions()
  const allowed = permission ? can(permission) : canAny(anyOf || [])
  return allowed ? children : fallback
}
