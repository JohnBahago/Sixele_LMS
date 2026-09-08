import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Users, ShieldCheck, BookOpen, ClipboardCheck, FileCheck2, Award, Settings, Bell, UserCircle, X, PanelLeftClose, PanelLeftOpen, UserPlus, GraduationCap, UserCog, PlayCircle, BarChart3, FolderOpen, UsersRound, CalendarDays, Target, Medal, MessageSquare } from 'lucide-react'
import { usePermissions } from '../../contexts/PermissionContext'
import { useAuth } from '../../contexts/AuthContext'
import { useTheme } from '../../contexts/ThemeContext'
const nav = [
  { label:'Dashboard', to:'/', icon:LayoutDashboard, permission:'reports.view' },
  { label:'Users', to:'/users', icon:Users, permission:'users.view' },
  { label:'Learners', to:'/learners', icon:GraduationCap, permission:'reports.view' },
  { label:'Instructor Portal', to:'/instructor', icon:UserCog, permission:'courses.view' },
  { label:'Teaching Cohorts', to:'/instructor/cohorts', icon:UsersRound, permission:'courses.view' },
  { label:'Instructors', to:'/instructors', icon:UserCog, permission:'instructors.view' },
  { label:'My Learning', to:'/learner', icon:PlayCircle, learner:true },
  { label:'My Cohorts', to:'/learner/cohorts', icon:CalendarDays, learner:true },
  { label:'My Courses', to:'/my-courses', icon:BookOpen, learner:true },
  { label:'My Progress', to:'/learner/progress', icon:Target, learner:true },
  { label:'Achievements', to:'/learner/achievements', icon:Medal, learner:true },
  { label:'My Grades', to:'/learner/grades', icon:Award, learner:true },
  { label:'Academic Record', to:'/learner/academic-record', icon:FileCheck2, learner:true },
  { label:'Enrollments', to:'/enrollments', icon:UserPlus, permission:'enrollments.view' },
  { label:'Cohorts & Live Training', to:'/cohorts', icon:UsersRound, permission:'cohorts.view' },
  { label:'Roles & Permissions', to:'/roles', icon:ShieldCheck, permission:'roles.view' },
  { label:'Courses', to:'/courses', icon:BookOpen, permission:'courses.view' },
  { label:'Activities', to:'/activities', icon:ClipboardCheck, permission:'activities.view' },
  { label:'Submissions', to:'/submissions', icon:FileCheck2, permission:'submissions.view' },
  { label:'Advanced Grading', to:'/grading', icon:Award, permission:'assessments.grade' },
  { label:'Gradebook', to:'/gradebook', icon:ClipboardCheck, permission:'reports.view' },
  { label:'Certificates', to:'/certificates', icon:Award, permission:'certificates.view' },
  { label:'Certificate Administration', to:'/admin/certificates', icon:Award, permission:'certificates.manage' },
  { label:'Notifications', to:'/notifications', icon:Bell, learner:true },
  { label:'Communication Center', to:'/communication', icon:MessageSquare, permission:'communications.view' },
  { label:'Notification Administration', to:'/admin/notifications', icon:Bell, permission:'communications.view' },
  { label:'My Profile', to:'/profile', icon:UserCircle, learner:true },
  { label:'Analytics & Reports', to:'/analytics', icon:BarChart3, permission:'reports.view' },
  { label:'Content Library', to:'/content', icon:FolderOpen, permission:'content.view' },
  { label:'Settings', to:'/settings', icon:Settings, permission:'settings.view' },
]
export default function Sidebar({open,onClose}) {
  const { can } = usePermissions(); const { user } = useAuth(); const { sidebarCollapsed, setSidebarCollapsed, sidebarStyle } = useTheme()
  const width = sidebarCollapsed ? 'w-20' : 'w-72'
  return <aside className={`fixed z-40 inset-y-0 left-0 ${width} text-white transition-all lg:static lg:translate-x-0 ${open?'translate-x-0':'-translate-x-full'} ${sidebarStyle==='soft'?'six-sidebar-soft':'six-sidebar-solid'}`}>
    <div className="h-full flex flex-col">
      <div className="h-20 px-4 flex items-center justify-between border-b border-white/10">
        {!sidebarCollapsed && <div><div className="text-2xl font-bold tracking-tight">Sixele</div><div className="text-xs text-white/55">Learning Management System</div></div>}
        <div className="flex items-center gap-1 ml-auto">
          <button className="hidden lg:flex p-2 rounded-lg hover:bg-white/10" onClick={()=>setSidebarCollapsed(!sidebarCollapsed)} title={sidebarCollapsed?'Expand sidebar':'Collapse sidebar'}>{sidebarCollapsed?<PanelLeftOpen size={19}/>:<PanelLeftClose size={19}/>}</button>
          <button className="lg:hidden p-2 rounded-lg hover:bg-white/10" onClick={onClose}><X size={20}/></button>
        </div>
      </div>
      <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
        {!sidebarCollapsed && <div className="text-[11px] uppercase tracking-wider text-white/45 px-3 py-3">Workspace</div>}
        {nav.filter(item=>item.learner ? (user?.is_learner || user?.role_names?.includes('Learner') || user?.roles?.some(r=>(r.name||r.label)==='Learner') || can('courses.view')) : can(item.permission)).map(item=>{const Icon=item.icon; return <NavLink key={item.to} to={item.to} onClick={onClose} title={sidebarCollapsed?item.label:''} className={({isActive})=>`flex items-center ${sidebarCollapsed?'justify-center':'gap-3'} px-3 py-3 rounded-xl text-sm transition ${isActive?'six-nav-active':'text-white/70 hover:bg-white/10 hover:text-white'}`}><Icon size={19}/>{!sidebarCollapsed&&<span>{item.label}</span>}</NavLink>})}
      </nav>
      {!sidebarCollapsed && <div className="p-4"><div className="rounded-2xl bg-white/8 p-4 text-xs text-white/55">Frontend v2.7<br/><span className="text-white/85">Theme-ready workspace</span></div></div>}
    </div>
  </aside>
}
