import { Building2, ChevronDown, Lock } from 'lucide-react'
import { useVenture } from '@/hooks/use-venture'

/**
 * The working venture for the whole dashboard. Locked (read-only label) for a
 * user limited to a single venture; hidden when there are no ventures yet.
 */
export function VentureSwitcher() {
  const { ventures, selected, select, locked, loading } = useVenture()
  if (loading || ventures.length === 0) return null

  const current = ventures.find((v) => v.key === selected)

  if (locked || ventures.length === 1) {
    return (
      <div
        className="mb-6 flex items-center gap-2 rounded-lg border border-border bg-surface-800 px-3 py-2 text-sm text-foreground"
        title={locked ? 'Your account works in this venture only' : undefined}
      >
        <Building2 className="h-4 w-4 shrink-0 text-brand-400" />
        <span className="truncate" dir="auto">
          {current?.name ?? selected}
        </span>
        {locked && <Lock className="ms-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
      </div>
    )
  }

  return (
    <label className="relative mb-6 block">
      <span className="sr-only">Venture</span>
      <Building2 className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-brand-400" />
      <select
        value={selected}
        onChange={(e) => select(e.target.value)}
        className="w-full appearance-none rounded-lg border border-border bg-surface-800 py-2 ps-9 pe-8 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
        dir="auto"
      >
        {ventures.map((v) => (
          <option key={v.key} value={v.key}>
            {v.name}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute end-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
    </label>
  )
}
