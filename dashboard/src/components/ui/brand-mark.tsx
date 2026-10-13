import { cn } from '@/lib/utils'

/**
 * The RealizeOS mark: a hi-vis sheet with its corner folded like a drawing
 * tab, an R drawn in ink, and the wordmark (Poppins, the brand's only use of it).
 */
export function BrandMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <svg viewBox="0 0 24 24" width={size} height={size} className="shrink-0" aria-hidden>
        <path d="M3 3h18v13l-5 5H3z" fill="var(--rz-accent)" />
        <path
          d="M16 21v-5h5"
          fill="none"
          stroke="var(--rz-accent-fg)"
          strokeWidth="1.5"
          strokeOpacity=".5"
        />
        <path
          d="M7.5 16V8h4.2a2.4 2.4 0 0 1 0 4.8H7.5m4.2 0L14.5 16"
          fill="none"
          stroke="var(--rz-accent-fg)"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span
        className="font-brand font-semibold tracking-tight text-foreground"
        style={{ fontSize: Math.round(size * 0.72) }}
      >
        RealizeOS
      </span>
    </span>
  )
}
