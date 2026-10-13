import { useRef, type KeyboardEvent, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { useIndicator } from '@/hooks/use-motion'

export interface TabItem<V extends string> {
  value: V
  label: ReactNode
  icon?: ReactNode
  count?: number
}

function moveFocus(
  e: KeyboardEvent<HTMLElement>,
  onPick: (i: number) => void,
  len: number,
  i: number,
) {
  const rtl = getComputedStyle(e.currentTarget).direction === 'rtl'
  const next = rtl ? 'ArrowLeft' : 'ArrowRight'
  const prev = rtl ? 'ArrowRight' : 'ArrowLeft'
  let to = -1
  if (e.key === next) to = (i + 1) % len
  else if (e.key === prev) to = (i - 1 + len) % len
  else if (e.key === 'Home') to = 0
  else if (e.key === 'End') to = len - 1
  if (to < 0) return
  e.preventDefault()
  onPick(to)
  const siblings =
    e.currentTarget.parentElement?.querySelectorAll<HTMLElement>('[role="tab"],button')
  siblings?.[to]?.focus()
}

function pick<V extends string>(items: TabItem<V>[], j: number, onChange: (v: V) => void) {
  const item = items[j]
  if (item) onChange(item.value)
}

/** Page-level views of the same thing. The ink glides to the chosen tab. */
export function Tabs<V extends string>({
  items,
  value,
  onChange,
  label,
  className,
}: {
  items: TabItem<V>[]
  value: V
  onChange: (v: V) => void
  label: string
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const ink = useIndicator(ref, '[aria-selected="true"]')
  return (
    <div ref={ref} role="tablist" aria-label={label} className={cn('rz-tabs', className)}>
      {items.map((t, i) => (
        <button
          key={t.value}
          role="tab"
          type="button"
          aria-selected={t.value === value}
          tabIndex={t.value === value ? 0 : -1}
          onClick={() => onChange(t.value)}
          onKeyDown={(e) => moveFocus(e, (j) => pick(items, j, onChange), items.length, i)}
        >
          {t.icon}
          {t.label}
          {t.count !== undefined && <span className="rz-tabs__count">{t.count}</span>}
        </button>
      ))}
      <span ref={ink} className="rz-tabs__ink" aria-hidden />
    </div>
  )
}

/** A small either/or switch inside a panel (List / Board, Day / Week). */
export function Segmented<V extends string>({
  items,
  value,
  onChange,
  label,
}: {
  items: TabItem<V>[]
  value: V
  onChange: (v: V) => void
  label: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const thumb = useIndicator(ref, '[aria-pressed="true"]')
  return (
    <div ref={ref} role="group" aria-label={label} className="rz-segmented">
      <span ref={thumb} className="rz-segmented__thumb" aria-hidden />
      {items.map((t, i) => (
        <button
          key={t.value}
          type="button"
          aria-pressed={t.value === value}
          onClick={() => onChange(t.value)}
          onKeyDown={(e) => moveFocus(e, (j) => pick(items, j, onChange), items.length, i)}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  )
}
