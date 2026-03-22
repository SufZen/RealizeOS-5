import { Activity, Bot, Zap, Wrench, User } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ActivityEvent {
  id: string
  venture_key: string
  actor_type: 'agent' | 'system' | 'user'
  actor_id: string
  action: string
  entity_type?: string
  entity_id?: string
  details?: string
  created_at: string
}

const actorIcons: Record<string, typeof Bot> = {
  agent: Bot,
  system: Zap,
  user: User,
}

const actionLabels: Record<string, string> = {
  message_received: 'Message received',
  agent_routed: 'Routed to agent',
  llm_called: 'LLM invoked',
  skill_executed: 'Skill executed',
  tool_used: 'Tool used',
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

interface ActivityFeedProps {
  events: ActivityEvent[]
  maxItems?: number
  className?: string
}

export function ActivityFeed({ events, maxItems = 20, className }: ActivityFeedProps) {
  const visible = events.slice(0, maxItems)

  if (visible.length === 0) {
    return (
      <div className={cn('text-center py-8 text-muted-foreground text-sm', className)}>
        <Activity className="h-8 w-8 mx-auto mb-2 opacity-50" />
        No activity yet
      </div>
    )
  }

  return (
    <div className={cn('space-y-1', className)}>
      {visible.map((event) => {
        const Icon = actorIcons[event.actor_type] || Wrench
        const label = actionLabels[event.action] || event.action
        return (
          <div
            key={event.id}
            className="flex items-start gap-3 rounded-lg px-3 py-2 text-sm hover:bg-surface-700/50 transition-colors"
          >
            <Icon className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
            <div className="flex-1 min-w-0">
              <span className="text-foreground">{label}</span>
              {event.entity_id && (
                <span className="text-muted-foreground ml-1">
                  &middot; {event.entity_id}
                </span>
              )}
              <span className="text-muted-foreground ml-1 text-xs">
                by {event.actor_id}
              </span>
            </div>
            <time className="text-xs text-muted-foreground shrink-0">
              {formatTime(event.created_at)}
            </time>
          </div>
        )
      })}
    </div>
  )
}
