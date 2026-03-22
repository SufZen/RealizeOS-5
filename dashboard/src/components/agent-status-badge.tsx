import { cn } from '@/lib/utils'

export type AgentStatus = 'idle' | 'running' | 'paused' | 'error'

const statusConfig: Record<AgentStatus, { label: string; color: string; dot: string }> = {
  idle: { label: 'Idle', color: 'text-emerald-400', dot: 'bg-emerald-400' },
  running: { label: 'Running', color: 'text-brand-400', dot: 'bg-brand-400 animate-pulse' },
  paused: { label: 'Paused', color: 'text-muted-foreground', dot: 'bg-muted-foreground' },
  error: { label: 'Error', color: 'text-red-400', dot: 'bg-red-400' },
}

interface AgentStatusBadgeProps {
  status: AgentStatus
  className?: string
}

export function AgentStatusBadge({ status, className }: AgentStatusBadgeProps) {
  const config = statusConfig[status] || statusConfig.idle
  return (
    <span className={cn('inline-flex items-center gap-1.5 text-xs font-medium', config.color, className)}>
      <span className={cn('h-2 w-2 rounded-full', config.dot)} />
      {config.label}
    </span>
  )
}
