import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import Sidebar from '../components/layout/Sidebar'
import Header from '../components/layout/Header'
export default function AppLayout(){ const [open,setOpen]=useState(false); return <div className="min-h-screen flex" style={{background:'var(--background)',color:'var(--text)'}}><Sidebar open={open} onClose={()=>setOpen(false)}/>{open&&<div className="fixed inset-0 bg-black/40 z-30 lg:hidden" onClick={()=>setOpen(false)}/>}<div className="flex-1 min-w-0"><Header onMenu={()=>setOpen(true)}/><main className="p-4 sm:p-6 lg:p-8"><Outlet/></main></div></div> }
