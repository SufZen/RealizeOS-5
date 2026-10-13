import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info' | 'agent'

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: Tone
  dot?: boolean
  outline?: boolean
}

/** A short status in words: "Held", "Approved", "3 sources". Sentence case. */
export function Badge({
  tone = 'neutral',
  dot,
  outline,
  className,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        'rz-badge',
        tone !== 'neutral' && `rz-badge--${tone}`,
        outline && 'rz-badge--outline',
        className,
      )}
      {...props}
    >
      {dot && <span className="rz-badge__dot" aria-hidden />}
      {children}
    </span>
  )
}

export type DotState = 'idle' | 'active' | 'review' | 'error' | 'routing' | 'brand' | 'agent'

/** A coloured dot. `live` makes it breathe: only while work is running right now. */
export function StatusDot({
  state = 'idle',
  live,
  label,
  className,
}: {
  state?: DotState
  live?: boolean
  label?: string
  className?: string
}) {
  return (
    <span
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        'rz-status-dot',
        state !== 'idle' && `rz-status-dot--${state}`,
        live && 'rz-status-dot--live',
        className,
      )}
    />
  )
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rz-kbd">{children}</kbd>
}
