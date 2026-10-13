import type { ReactNode } from 'react'
import { ArrowDownRight, ArrowUpRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useCountUp } from '@/hooks/use-motion'

interface StatProps {
  label: ReactNode
  value: number
  /** Format the (animating) number for display. Defaults to whole numbers in the page locale. */
  format?: (n: number) => string
  unit?: ReactNode
  /** Change against the previous period; sign decides colour unless `goodWhen` flips it. */
  delta?: number
  deltaLabel?: ReactNode
  goodWhen?: 'up' | 'down'
  /** Where this figure came from: a SourceRef, or a short note. Figures without a source are guesses. */
  source?: ReactNode
  className?: string
}

/** A figure that matters. It counts up when it changes, and it says where it came from. */
export function Stat({
  label,
  value,
  format,
  unit,
  delta,
  deltaLabel,
  goodWhen = 'up',
  source,
  className,
}: StatProps) {
  const shown = useCountUp(value)
  const text = format ? format(shown) : Math.round(shown).toLocaleString()
  const good = delta !== undefined && (goodWhen === 'up' ? delta >= 0 : delta <= 0)
  return (
    <div className={cn('rz-stat', className)}>
      <span className="rz-stat__label">
        {label}
        {source}
      </span>
      <span className="rz-stat__value">
        {text}
        {unit && <span className="rz-stat__unit">{unit}</span>}
      </span>
      {delta !== undefined && (
        <span
          className={cn('rz-stat__delta', good ? 'rz-stat__delta--up' : 'rz-stat__delta--down')}
        >
          {delta >= 0 ? (
            <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
          ) : (
            <ArrowDownRight className="h-3.5 w-3.5" aria-hidden />
          )}
          {Math.abs(delta).toLocaleString()}%
          {deltaLabel && <span className="text-subtle-foreground">{deltaLabel}</span>}
        </span>
      )}
    </div>
  )
}
