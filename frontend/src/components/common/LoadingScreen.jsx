export default function LoadingScreen() {
  return <div className="min-h-screen flex items-center justify-center" style={{ background:'var(--background)', color:'var(--text)' }}><div className="text-center"><div className="w-10 h-10 rounded-full border-4 border-current border-r-transparent animate-spin mx-auto six-primary-text"/><div className="mt-4 text-sm six-muted">Loading Sixele LMS…</div></div></div>
}
