import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Eye, EyeOff, Loader2 } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { useTheme } from '../../contexts/ThemeContext'

export default function Login(){
 const {login}=useAuth(); const nav=useNavigate(); const {theme}=useTheme()
 const [email,setEmail]=useState(''); const [password,setPassword]=useState(''); const [show,setShow]=useState(false); const [busy,setBusy]=useState(false); const [error,setError]=useState('')
 const submit=async e=>{e.preventDefault();setError('');setBusy(true);try{await login(email,password);nav('/')}catch(err){setError(err.message)}finally{setBusy(false)}}
 return <div className="min-h-screen flex items-center justify-center p-6" style={{background:'var(--background)',color:'var(--text)'}}><div className="w-full max-w-md">
  <div className="text-center mb-8"><div className="text-4xl font-bold six-primary-text">Sixele</div><p className="six-muted mt-2">Learning Management System</p></div>
  <form onSubmit={submit} className="six-surface border p-8 shadow-xl"><h1 className="text-2xl font-bold">Welcome back</h1><p className="six-muted mt-1 mb-7">Sign in to continue to your workspace.</p>
   {error&&<div className="mb-5 rounded-xl border border-red-200 bg-red-50 text-red-700 text-sm p-3">{error}</div>}
   <label className="text-sm font-medium">Email</label><input value={email} onChange={e=>setEmail(e.target.value)} type="email" required autoComplete="email" className="six-input w-full mt-2 mb-5 h-12 px-4 rounded-xl outline-none" placeholder="you@example.com"/>
   <label className="text-sm font-medium">Password</label><div className="relative mt-2 mb-6"><input value={password} onChange={e=>setPassword(e.target.value)} type={show?'text':'password'} required autoComplete="current-password" className="six-input w-full h-12 px-4 pr-12 rounded-xl outline-none" placeholder="Your password"/><button type="button" onClick={()=>setShow(!show)} className="absolute right-3 top-3 six-muted">{show?<EyeOff size={20}/>:<Eye size={20}/>}</button></div>
   <button disabled={busy} className="w-full h-12 rounded-xl six-button font-semibold flex items-center justify-center gap-2">{busy&&<Loader2 size={18} className="animate-spin"/>}{busy?'Signing in…':'Sign in'}</button>
   <p className="text-center text-sm six-muted mt-6">No account? <Link className="six-primary-text font-semibold" to="/register">Create one</Link></p>
   <p className="text-center text-xs six-muted mt-4">Connected API • Theme: {theme}</p>
  </form></div></div>
}
