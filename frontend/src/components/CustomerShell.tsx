import { Link, Outlet } from 'react-router'
import { Headset, Lock } from 'lucide-react'
import { Logo } from './ui'

export default function CustomerShell() {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/80 backdrop-blur print:hidden">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link to="/" aria-label="ClaimShield home">
            <Logo />
          </Link>
          <div className="flex items-center gap-5 text-sm text-slate-600">
            <span className="hidden items-center gap-1.5 sm:flex">
              <Lock className="size-4 text-emerald-600" aria-hidden /> Secure claim submission
            </span>
            <span className="flex items-center gap-1.5">
              <Headset className="size-4 text-indigo-600" aria-hidden /> 1800-000-0000
            </span>
          </div>
        </div>
      </header>
      <main className="relative flex-1">
        <div className="bg-grid pointer-events-none absolute inset-x-0 top-0 h-80 [mask-image:linear-gradient(to_bottom,black,transparent)] print:hidden" />
        <div className="relative mx-auto max-w-6xl px-4 py-8 sm:px-6 sm:py-10">
          <Outlet />
        </div>
      </main>
      <footer className="border-t border-slate-200 bg-white py-6 text-center text-xs text-slate-500 print:hidden">
        Assure Health Insurance (fictional demo) · Claims are checked by automated verification before settlement.
      </footer>
    </div>
  )
}
