import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'
import { LoaderCircle, ShieldCheck } from 'lucide-react'
import { cn } from '../lib/utils'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'dark'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
}

export function Button({ variant = 'primary', size = 'md', loading, className, children, disabled, type = 'button', ...rest }: ButtonProps) {
  const v = {
    primary: 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/25 hover:bg-indigo-700',
    secondary: 'bg-white text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50',
    ghost: 'text-slate-600 hover:bg-slate-100',
    danger: 'bg-rose-600 text-white hover:bg-rose-700',
    dark: 'bg-white/10 text-white ring-1 ring-inset ring-white/15 hover:bg-white/20',
  }[variant]
  const s = { sm: 'h-8 px-3 text-sm', md: 'h-10 px-4 text-sm', lg: 'h-12 px-6 text-base' }[size]
  return (
    <button
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-colors',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600',
        'disabled:cursor-not-allowed disabled:opacity-50',
        v,
        s,
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <LoaderCircle className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={cn('rounded-2xl bg-white shadow-sm ring-1 ring-slate-200', className)}>{children}</div>
}

export function Field({
  label,
  hint,
  error,
  children,
  className,
  htmlFor,
}: {
  label: string
  hint?: ReactNode
  error?: string
  children: ReactNode
  className?: string
  htmlFor?: string
}) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="mb-1.5 block text-sm font-medium text-slate-700">
        {label}
      </label>
      {children}
      {error ? (
        <p className="mt-1 text-xs text-rose-600" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="mt-1 text-xs text-slate-500">{hint}</p>
      ) : null}
    </div>
  )
}

export function Input({ className, invalid, ...rest }: InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={cn(
        'block h-10 w-full rounded-xl border-0 bg-white px-3 text-sm text-slate-900 ring-1 ring-inset placeholder:text-slate-400',
        'focus:outline-none focus:ring-2 focus:ring-inset disabled:bg-slate-50 disabled:text-slate-500',
        invalid ? 'ring-rose-400 focus:ring-rose-500' : 'ring-slate-300 focus:ring-indigo-600',
        className,
      )}
      {...rest}
    />
  )
}

export type Tone = 'slate' | 'green' | 'amber' | 'red' | 'indigo' | 'violet' | 'sky'

export const TONE: Record<Tone, string> = {
  slate: 'bg-slate-100 text-slate-700 ring-slate-200',
  green: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  amber: 'bg-amber-50 text-amber-800 ring-amber-200',
  red: 'bg-rose-50 text-rose-700 ring-rose-200',
  indigo: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
  violet: 'bg-violet-50 text-violet-700 ring-violet-200',
  sky: 'bg-sky-50 text-sky-700 ring-sky-200',
}

export function Badge({ tone = 'slate', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset', TONE[tone], className)}>
      {children}
    </span>
  )
}

export function Alert({ tone = 'red', children, className }: { tone?: 'red' | 'amber' | 'indigo'; children: ReactNode; className?: string }) {
  const t = {
    red: 'bg-rose-50 text-rose-800 ring-rose-200',
    amber: 'bg-amber-50 text-amber-900 ring-amber-200',
    indigo: 'bg-indigo-50 text-indigo-900 ring-indigo-200',
  }[tone]
  return (
    <div role={tone === 'red' ? 'alert' : undefined} className={cn('rounded-xl px-4 py-3 text-sm ring-1 ring-inset', t, className)}>
      {children}
    </div>
  )
}

export function Logo({ dark = false, subtitle = 'by Assure Health' }: { dark?: boolean; subtitle?: string }) {
  return (
    <div className="flex items-center gap-2.5">
      <div className="grid size-9 place-items-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 shadow-md shadow-indigo-500/30">
        <ShieldCheck className="size-5 text-white" aria-hidden />
      </div>
      <div className="leading-tight">
        <div className={cn('text-base font-semibold tracking-tight', dark ? 'text-white' : 'text-slate-900')}>ClaimShield</div>
        <div className={cn('text-xs', dark ? 'text-slate-400' : 'text-slate-500')}>{subtitle}</div>
      </div>
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={cn('size-5 animate-spin text-indigo-600', className)} aria-label="Loading" />
}
