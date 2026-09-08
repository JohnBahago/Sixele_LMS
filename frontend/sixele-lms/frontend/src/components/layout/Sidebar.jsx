import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Users, ShieldCheck, BookOpen, ClipboardCheck, FileCheck2, Award, Settings, X } from 'lucide-react'
import { usePermissions } from '../../contexts/PermissionContext'

const nav = [
  { label:'Dashboard', to:'/', icon:LayoutDashboard, permission:'reports.view' },
  { label:'Users', to:'/users', icon:Users, permission:'users.view' },
  { label:'Roles & Permissions', to:'/roles', icon:ShieldCheck, permission:'roles.view' },
  { label:'Courses', to:'/courses', icon:BookOpen, permission:'courses.view' },
  { label:'Activities', to:'/activities', icon:ClipboardCheck, permission:'activities.view' },
  { label:'Submissions', to:'/submissions', icon:FileCheck2, permission:'submissions.view' },
  { label:'Certificates', to:'/certificates', icon:Award, permission:'certificates.view' },
  { label:'Settings', to:'/settings', icon:Settings, permission:'settings.view' },
]
export default function Sidebar({open,onClose}) {
  const { can } = usePermissions()
  return <aside className={`fixed z-40 inset-y-0 left-0 w-72 bg-slate-950 text-white transition-transform lg:static lg:translate-x-0 ${open?'translate-x-0':'-translate-x-full'}`}>
    <div className="h-full flex flex-col">
      <div className="h-20 px-6 flex items-center justify-between border-b border-white/10">
        <div><div className="text-2xl font-bold tracking-tight">Sixele</div><div className="text-xs text-slate-400">Learning Management System</div></div>
        <button className="lg:hidden p-2 rounded-lg hover:bg-white/10" onClick={onClose}><X size={20}/></button>
      </div>
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        <div className="text-[11px] uppercase tracking-wider text-slate-500 px-3 py-3">Workspace</div>
        {nav.filter(item=>can(item.permission)).map(item=>{const Icon=item.icon; return <NavLink key={item.to} to={item.to} onClick={onClose} className={({isActive})=>`flex items-center gap-3 px-3 py-3 rounded-xl text-sm transition ${isActive?'bg-emerald-500 text-white shadow-lg shadow-emerald-950/30':'text-slate-300 hover:bg-white/10 hover:text-white'}`}><Icon size={19}/><span>{item.label}</span></NavLink>})}
      </nav>
      <div className="p-4"><div className="rounded-2xl bg-white/5 p-4 text-xs text-slate-400">Frontend foundation<br/><span className="text-slate-200">API-ready architecture</span></div></div>
    </div>
  </aside>
}
