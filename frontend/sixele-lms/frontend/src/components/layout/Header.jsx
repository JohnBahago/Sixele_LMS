import { Bell, Menu, Search } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
export default function Header({onMenu}) {
 const {user}=useAuth()
 return <header className="h-20 bg-white border-b border-slate-200 flex items-center gap-4 px-4 sm:px-6">
  <button onClick={onMenu} className="lg:hidden p-2 rounded-xl hover:bg-slate-100"><Menu size={22}/></button>
  <div className="hidden md:flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 h-11 w-full max-w-md"><Search size={18} className="text-slate-400"/><input className="bg-transparent outline-none w-full text-sm" placeholder="Search Sixele..."/></div>
  <div className="ml-auto flex items-center gap-3"><button className="p-2.5 rounded-xl hover:bg-slate-100 relative"><Bell size={20}/><span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-emerald-500"/></button><div className="flex items-center gap-3 pl-2"><div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-semibold">{user?.name?.[0]||'S'}</div><div className="hidden sm:block"><div className="text-sm font-semibold">{user?.name}</div><div className="text-xs text-slate-500">{user?.roles?.join(' · ')}</div></div></div></div>
 </header>
}
