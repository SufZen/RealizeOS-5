import { Building2, Lock } from 'lucide-react'
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
        className="mb-4 flex items-center gap-2 h-9 rounded-[5px] border border-border bg-surface-800 px-2.5 text-[13px] font-medium text-foreground"
        title={locked ? 'Your account works in this venture only' : undefined}
      >
        <Building2 className="h-4 w-4 shrink-0 text-subtle-foreground" />
        <span className="truncate" dir="auto">
          {current?.name ?? selected}
        </span>
        {locked && <Lock className="ms-auto h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
      </div>
    )
  }

  return (
    <label className="relative mb-4 block">
      <span className="sr-only">Venture</span>
      <Building2 className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-subtle-foreground z-10" />
      <select
        value={selected}
        onChange={(e) => select(e.target.value)}
        className="rz-select h-9 ps-9 font-medium"
        dir="auto"
      >
        {ventures.map((v) => (
          <option key={v.key} value={v.key}>
            {v.name}
          </option>
        ))}
      </select>
    </label>
  )
}
