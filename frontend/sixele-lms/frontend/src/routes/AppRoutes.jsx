import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AppLayout from '../layouts/AppLayout'
import Login from '../pages/auth/Login'
import Register from '../pages/auth/Register'
import Dashboard from '../pages/dashboard/Dashboard'
import RoleManagement from '../pages/roles/RoleManagement'
import Placeholder from '../pages/Placeholder'
import { useAuth } from '../contexts/AuthContext'
function Protected(){const {user}=useAuth(); return user?<AppLayout/>:<Navigate to="/login" replace/>}
export default function AppRoutes(){return <BrowserRouter><Routes><Route path="/login" element={<Login/>}/><Route path="/register" element={<Register/>}/><Route element={<Protected/>}><Route path="/" element={<Dashboard/>}/><Route path="/roles" element={<RoleManagement/>}/><Route path="/users" element={<Placeholder title="User Management"/>}/><Route path="/courses" element={<Placeholder title="Course Management"/>}/><Route path="/activities" element={<Placeholder title="Hands-on Activities"/>}/><Route path="/submissions" element={<Placeholder title="Submission Management"/>}/><Route path="/certificates" element={<Placeholder title="Certificates"/>}/><Route path="/settings" element={<Placeholder title="System Settings"/>}/></Route></Routes></BrowserRouter>}
