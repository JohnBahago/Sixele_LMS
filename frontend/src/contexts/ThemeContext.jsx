import { createContext, useContext, useEffect, useMemo, useState } from 'react'

export const themes = {
  sixele: { name: 'Sixele Red', description: 'Official Sixele red and grey', primary: '#b91c1c', sidebar: '#292929', surface: '#ffffff', background: '#f3f4f6' },
  crimson: { name: 'Crimson', description: 'Deep red with slate grey', primary: '#991b1b', sidebar: '#27272a', surface: '#ffffff', background: '#f4f4f5' },
  ruby: { name: 'Ruby', description: 'Bright modern red and cool grey', primary: '#dc2626', sidebar: '#374151', surface: '#ffffff', background: '#f1f5f9' },
  graphite: { name: 'Graphite', description: 'Graphite interface with red accents', primary: '#52525b', sidebar: '#18181b', surface: '#ffffff', background: '#f4f4f5' },
  midnight: { name: 'Midnight', description: 'Dark red and charcoal workspace', primary: '#ef4444', sidebar: '#111827', surface: '#1f2937', background: '#111827' },
  cloud: { name: 'Cloud', description: 'Clean light corporate workspace', primary: '#b91c1c', sidebar: '#4b5563', surface: '#ffffff', background: '#f8fafc' },
  rosewood: { name: 'Rosewood', description: 'Elegant deep red and warm grey', primary: '#9f1239', sidebar: '#3f3f46', surface: '#fffaf9', background: '#f5f3f2' },
}

const ThemeContext = createContext(null)
const read = (key, fallback) => { try { return localStorage.getItem(key) || fallback } catch { return fallback } }

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(() => read('sixele.theme', 'sixele'))
  const [mode, setMode] = useState(() => read('sixele.mode', 'light'))
  const [density, setDensity] = useState(() => read('sixele.density', 'comfortable'))
  const [radius, setRadius] = useState(() => read('sixele.radius', 'rounded'))
  const [sidebarStyle, setSidebarStyle] = useState(() => read('sixele.sidebarStyle', 'solid'))
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => read('sixele.sidebarCollapsed', 'false') === 'true')

  useEffect(() => { localStorage.setItem('sixele.theme', theme); document.body.className = `theme-${theme} mode-${mode} density-${density} radius-${radius}` }, [theme, mode, density, radius])
  useEffect(() => localStorage.setItem('sixele.mode', mode), [mode])
  useEffect(() => localStorage.setItem('sixele.density', density), [density])
  useEffect(() => localStorage.setItem('sixele.radius', radius), [radius])
  useEffect(() => localStorage.setItem('sixele.sidebarStyle', sidebarStyle), [sidebarStyle])
  useEffect(() => localStorage.setItem('sixele.sidebarCollapsed', String(sidebarCollapsed)), [sidebarCollapsed])

  const value = useMemo(() => ({ theme, setTheme, mode, setMode, density, setDensity, radius, setRadius, sidebarStyle, setSidebarStyle, sidebarCollapsed, setSidebarCollapsed, themes }), [theme, mode, density, radius, sidebarStyle, sidebarCollapsed])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
