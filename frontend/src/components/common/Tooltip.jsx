import { useState } from 'react'
export default function Tooltip({text,children,side='top'}){
  const [show,setShow]=useState(false)
  if(!text) return children
  return <span className="relative inline-flex" onMouseEnter={()=>setShow(true)} onMouseLeave={()=>setShow(false)} onFocus={()=>setShow(true)} onBlur={()=>setShow(false)}>
    {children}
    {show && <span role="tooltip" className={`six-tooltip absolute z-50 whitespace-nowrap rounded-lg bg-zinc-900 px-2.5 py-1.5 text-xs text-white shadow-xl ${side==='bottom'?'top-full mt-2':side==='left'?'right-full mr-2':'bottom-full mb-2'} left-1/2 -translate-x-1/2`}>{text}</span>}
  </span>
}
