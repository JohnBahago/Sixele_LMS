import { AuthProvider } from './contexts/AuthContext'
import { PermissionProvider } from './contexts/PermissionContext'
import { ThemeProvider } from './contexts/ThemeContext'
import AppRoutes from './routes/AppRoutes'
export default function App(){return <ThemeProvider><AuthProvider><PermissionProvider><AppRoutes/></PermissionProvider></AuthProvider></ThemeProvider>}
