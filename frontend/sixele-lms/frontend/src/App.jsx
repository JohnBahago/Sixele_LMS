import { AuthProvider } from './contexts/AuthContext'
import { PermissionProvider } from './contexts/PermissionContext'
import AppRoutes from './routes/AppRoutes'
export default function App(){return <AuthProvider><PermissionProvider><AppRoutes/></PermissionProvider></AuthProvider>}
