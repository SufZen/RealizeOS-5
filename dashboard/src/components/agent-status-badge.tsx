import { cn } from '@/lib/utils'
import { StatusDot, type DotState } from '@/components/ui/badge'

export type AgentStatus = 'idle' | 'running' | 'paused' | 'error'

/** Idle is not "healthy": it is quiet. Only running work breathes. */
const statusConfig: Record<AgentStatus, { label: string; dot: DotState; color: string }> = {
  idle: { label: 'Idle', dot: 'idle', color: 'text-muted-foreground' },
  running: { label: 'Running', dot: 'agent', color: 'text-violet-400' },
  paused: { label: 'Paused', dot: 'idle', color: 'text-muted-foreground' },
  error: { label: 'Error', dot: 'error', color: 'text-red-400' },
}

interface AgentStatusBadgeProps {
  status: AgentStatus
  className?: string
}

export function AgentStatusBadge({ status, className }: AgentStatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.idle
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 text-xs font-medium',
        config.color,
        className,
      )}
    >
      <StatusDot state={config.dot} live={status === 'running'} />
      {config.label}
    </span>
  )
}
