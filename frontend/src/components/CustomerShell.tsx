import { Link, Outlet } from 'react-router'
import { Headset } from 'lucide-react'
import { Logo } from './ui'

export default function CustomerShell() {
  return (
    <div className="flex min-h-dvh flex-col bg-white">
      <header className="border-b border-slate-200 bg-white print:hidden">
        <div className="flex h-24 w-full items-center justify-between px-4 sm:px-8 lg:px-12">
          <Link to="/" aria-label="ClaimShield home">
            <Logo />
          </Link>
          <a
            href="tel:18000000000"
            className="inline-flex h-9 items-center gap-2 rounded-sm bg-white px-5 text-sm font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-600 hover:bg-indigo-50"
          >
            <Headset className="size-4" aria-hidden /> Contact us
          </a>
        </div>
      </header>
      <main className="flex-1">
        <div className="w-full px-4 py-8 sm:px-8 sm:py-10 lg:px-12">
          <Outlet />
        </div>
      </main>
      <div className="print:hidden">
        <div className="w-full px-4 pb-8 sm:px-8 lg:px-12">
          <p className="bg-slate-100 px-5 py-4 text-sm text-slate-700">
            If you have any questions about your claim, please call the claims helpline on <b>1800-000-0000</b>. Lines are open Monday to Friday 8am to 6pm.
            Claims are received and checked by automated analysis before any decision.
          </p>
        </div>
        <footer className="bg-indigo-900 py-8 text-white">
          <div className="flex w-full flex-col gap-4 px-4 sm:flex-row sm:items-center sm:gap-8 sm:px-8 lg:px-12">
            <Logo dark subtitle="" />
            <p className="text-xs text-indigo-100">Assure Health Insurance (fictional demo) · Privacy and cookies · Accessibility · Legal notices</p>
          </div>
        </footer>
      </div>
    </div>
  )
}