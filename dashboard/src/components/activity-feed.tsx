import { cn } from '@/lib/utils'
import { EmptyState } from '@/components/ui/empty-state'

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

const actionLabels: Record<string, string> = {
  message_received: 'Message received',
  agent_routed: 'Routed to agent',
  llm_called: 'Model called',
  skill_executed: 'Skill run',
  tool_used: 'Tool used',
}

/** "venture_created" → "Venture created" for actions without a hand-written label. */
function humanize(action: string): string {
  const text = action.replace(/[_.-]+/g, ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

/** People are round, agents are sheet tabs, the system is a small square. */
function ActorMark({ type, id }: { type: ActivityEvent['actor_type']; id: string }) {
  const initials =
    id
      .replace(/[^\p{L}\p{N}]/gu, '')
      .slice(0, 2)
      .toUpperCase() || '?'
  if (type === 'agent')
    return (
      <span className="rz-avatar rz-avatar--agent rz-avatar--sm" aria-hidden>
        {initials}
      </span>
    )
  if (type === 'user')
    return (
      <span className="rz-avatar rz-avatar--sm" aria-hidden>
        {initials}
      </span>
    )
  return (
    <span
      className="grid h-[22px] w-[22px] shrink-0 place-items-center rounded-[4px] bg-surface-700 text-[9px] font-semibold text-subtle-foreground"
      aria-hidden
    >
      OS
    </span>
  )
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
      <div className={cn('p-4', className)}>
        <EmptyState
          art="activity"
          title="No activity yet"
          body="When agents read documents, run skills or ask for approval, each step shows up here."
        />
      </div>
    )
  }

  return (
    <ol className={cn('m-0 list-none p-1.5', className)}>
      {visible.map((event) => {
        const label = actionLabels[event.action] || humanize(event.action)
        return (
          <li
            key={event.id}
            className="flex items-center gap-3 rounded-[7px] px-2.5 py-2 text-[13px] transition-colors hover:bg-surface-700/50"
          >
            <ActorMark type={event.actor_type} id={event.actor_id} />
            <div className="min-w-0 flex-1 truncate">
              <span className="text-foreground">{label}</span>
              {event.entity_id && (
                <span dir="auto" className="ms-1.5 text-muted-foreground">
                  {event.entity_id}
                </span>
              )}
              <span className="ms-1.5 text-xs text-subtle-foreground">by {event.actor_id}</span>
            </div>
            <time
              dateTime={event.created_at}
              className="shrink-0 text-xs tabular text-subtle-foreground"
            >
              {formatTime(event.created_at)}
            </time>
          </li>
        )
      })}
    </ol>
  )
}
