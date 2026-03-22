import { Briefcase, Users, Zap, Clock } from 'lucide-react'
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

export function VentureHealthCard({
  name,
  ventureKey,
  agentCount,
  skillCount,
  lastActivity,
  className,
  onClick,
}: VentureHealthCardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card p-4 transition-colors',
        onClick && 'cursor-pointer hover:border-brand-400/50',
        className,
      )}
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Briefcase className="h-4 w-4 text-brand-400" />
          <h3 className="text-sm font-semibold text-foreground">{name}</h3>
        </div>
        <span className="text-xs text-muted-foreground font-mono">{ventureKey}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div className="flex items-center gap-1 text-muted-foreground">
          <Users className="h-3 w-3" />
          <span>{agentCount} agents</span>
        </div>
        <div className="flex items-center gap-1 text-muted-foreground">
          <Zap className="h-3 w-3" />
          <span>{skillCount} skills</span>
        </div>
        {lastActivity && (
          <div className="flex items-center gap-1 text-muted-foreground">
            <Clock className="h-3 w-3" />
            <span>{lastActivity}</span>
          </div>
        )}
      </div>
    </div>
  )
}
