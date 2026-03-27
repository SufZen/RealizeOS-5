import { useState, useEffect, useCallback } from 'react'
import { Activity, Filter, RefreshCw } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { useDebounce } from '@/hooks/use-debounce'
import { ActivityFeed, type ActivityEvent } from '@/components/activity-feed'
import { createActivityStream } from '@/lib/api'
import { cn } from '@/lib/utils'

interface ActivityResponse {
  events: ActivityEvent[]
  total: number
  limit: number
  offset: number
}

function isActivityEvent(data: unknown): data is ActivityEvent {
  if (!data || typeof data !== 'object') return false
  const d = data as Record<string, unknown>
  return (
    typeof d.id === 'string' &&
    typeof d.action === 'string' &&
    typeof d.actor_id === 'string' &&
    typeof d.created_at === 'string'
  )
}

function extractEvents(data: unknown): ActivityEvent[] {
  if (!data || typeof data !== 'object') return []
  const obj = data as Record<string, unknown>
  if (Array.isArray(obj.events)) return obj.events
  if (Array.isArray(obj.recent_activity)) return obj.recent_activity
  return []
}

function extractTotal(data: unknown): number | null {
  if (!data || typeof data !== 'object') return null
  const obj = data as Record<string, unknown>
  return typeof obj.total === 'number' ? obj.total : null
}

export default function ActivityPage() {
  const [ventureKey, setVentureKey] = useState('')
  const [actorFilter, setActorFilter] = useState('')
  const [actionFilter, setActionFilter] = useState('')
  const [newCount, setNewCount] = useState(0)
  const [liveEvents, setLiveEvents] = useState<ActivityEvent[]>([])

  const debouncedVentureKey = useDebounce(ventureKey, 400)
  const debouncedActorFilter = useDebounce(actorFilter, 400)

  const params = new URLSearchParams()
  if (debouncedVentureKey) params.set('venture_key', debouncedVentureKey)
  if (debouncedActorFilter) params.set('actor_id', debouncedActorFilter)
  if (actionFilter) params.set('action', actionFilter)

  // For now, use a default venture or all
  const queryPath = debouncedVentureKey
    ? `/ventures/${debouncedVentureKey}/activity?${params.toString()}`
    : '/ventures/_all/activity'

  const { data, loading, error, refetch } = useApi<ActivityResponse>(
    debouncedVentureKey ? queryPath : '/dashboard',
  )

  // SSE for live updates
  useEffect(() => {
    const source = createActivityStream((event) => {
      if (isActivityEvent(event)) {
        setLiveEvents((prev) => [event, ...prev].slice(0, 50))
        setNewCount((c) => c + 1)
      }
    })

    return () => source.close()
  }, [])

  const handleRefresh = useCallback(() => {
    setNewCount(0)
    setLiveEvents([])
    refetch()
  }, [refetch])

  // Combine persisted + live events
  const persistedEvents = extractEvents(data)
  const allEvents = [...liveEvents, ...persistedEvents]
  // Deduplicate by ID
  const seen = new Set<string>()
  const uniqueEvents = allEvents.filter((e) => {
    if (!e.id || seen.has(e.id)) return false
    seen.add(e.id)
    return true
  })

  const totalCount = extractTotal(data)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Activity</h1>
        </div>
        <div className="flex items-center gap-2">
          {newCount > 0 && (
            <span className="text-xs bg-brand-400/10 text-brand-400 px-2 py-1 rounded-full font-medium">
              {newCount} new
            </span>
          )}
          <button
            onClick={handleRefresh}
            className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            title="Refresh"
            aria-label="Refresh activity"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Filter className="h-3.5 w-3.5" />
          <span>Filters:</span>
        </div>
        <input
          type="text"
          placeholder="Venture key"
          value={ventureKey}
          onChange={(e) => setVentureKey(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground',
            'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        />
        <input
          type="text"
          placeholder="Agent"
          value={actorFilter}
          onChange={(e) => setActorFilter(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground',
            'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        />
        <select
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground',
            'focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        >
          <option value="">All actions</option>
          <option value="message_received">Message Received</option>
          <option value="agent_routed">Agent Routed</option>
          <option value="llm_called">LLM Called</option>
          <option value="skill_executed">Skill Executed</option>
          <option value="tool_used">Tool Used</option>
          <option value="status_changed">Status Changed</option>
        </select>
      </div>

      {/* Event list */}
      <div className="rounded-xl border border-border bg-card">
        {loading && !uniqueEvents.length ? (
          <div className="p-8 text-center text-muted-foreground text-sm">Loading events...</div>
        ) : error && !uniqueEvents.length ? (
          <div className="p-8 text-center text-red-400 text-sm">{error}</div>
        ) : (
          <ActivityFeed events={uniqueEvents} maxItems={100} />
        )}
      </div>

      {totalCount != null && (
        <p className="text-xs text-muted-foreground text-center">
          Showing {uniqueEvents.length} of {totalCount} events
        </p>
      )}
    </div>
  )
}
