import { Building2, Users, Zap, Clock, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

interface VentureHealthCardProps {
  name: string
  ventureKey: string
  agentCount: number
  skillCount: number
  lastActivity?: string
  className?: string
  onClick?: () => void
}

/** A venture at a glance. A real button when it navigates, so it works from the keyboard. */
export function VentureHealthCard({
  name,
  ventureKey,
  agentCount,
  skillCount,
  lastActivity,
  className,
  onClick,
}: VentureHealthCardProps) {
  const body = (
    <>
      <div className="flex items-start gap-2.5">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-[7px] bg-surface-700 text-subtle-foreground">
          <Building2 className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 dir="auto" className="m-0 truncate text-sm font-semibold text-foreground">
            {name}
          </h3>
          <span className="text-xs text-subtle-foreground">{ventureKey}</span>
        </div>
        {onClick && (
          <ChevronRight className="h-4 w-4 shrink-0 text-subtle-foreground opacity-0 transition-opacity group-hover:opacity-100 rtl:rotate-180" />
        )}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <Users className="h-3.5 w-3.5" />
          {agentCount} agents
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Zap className="h-3.5 w-3.5" />
          {skillCount} skills
        </span>
        {lastActivity && (
          <span className="inline-flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            {lastActivity}
          </span>
        )}
      </div>
    </>
  )

  if (!onClick) return <div className={cn('rz-card', className)}>{body}</div>
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn('rz-card rz-pressable group w-full cursor-pointer text-start', className)}
    >
      {body}
    </button>
  )
}
