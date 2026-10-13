import { useState, useMemo } from 'react'
import {
  Route as RouteIcon,
  BarChart3,
  Bot,
  Filter,
  RefreshCw,
  UserCheck,
  Search,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { ErrorState } from '@/components/ui/error-state'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types — what GET /routing/analytics actually returns                */
/* ------------------------------------------------------------------ */

/** How an agent was chosen for a message. */
type RouteMethod = 'requested' | 'keyword' | 'default' | 'fallback' | 'test'

interface RoutingDecision {
  id: string
  timestamp: string
  system_key: string
  selected_agent: string
  method: RouteMethod
  /** Only routing tests keep the message; real chats don't. */
  message_preview: string
}

interface AgentStat {
  agent_key: string
  total_calls: number
  fallback_rate: number
}

interface RoutingData {
  decisions: RoutingDecision[]
  agent_stats: AgentStat[]
  method_counts: Partial<Record<RouteMethod, number>>
  total_decisions: number
}

const RANGE_HOURS = { '1h': 1, '24h': 24, '7d': 24 * 7, '30d': 24 * 30 } as const

const METHOD_LABELS: Record<RouteMethod, string> = {
  requested: 'chosen by user',
  keyword: 'keyword match',
  default: 'default agent',
  fallback: 'fallback',
  test: 'routing test',
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

export default function RoutingPage() {
  const [timeRange, setTimeRange] = useState<keyof typeof RANGE_HOURS>('24h')
  const [agentFilter, setAgentFilter] = useState<string>('')
  const {
    data: rawData,
    loading,
    error,
    refetch,
  } = useApi<RoutingData>(`/routing/analytics?hours=${RANGE_HOURS[timeRange]}&limit=200`)

  // Normalize data with safe defaults to prevent crashes
  const data = useMemo<RoutingData | null>(() => {
    if (!rawData) return null
    return {
      decisions: rawData.decisions ?? [],
      agent_stats: rawData.agent_stats ?? [],
      method_counts: rawData.method_counts ?? {},
      total_decisions: rawData.total_decisions ?? 0,
    }
  }, [rawData])

  const filteredDecisions = useMemo(() => {
    if (!data?.decisions) return []
    let result = data.decisions
    if (agentFilter) {
      result = result.filter((d) => d.selected_agent === agentFilter)
    }
    return result.slice(0, 50)
  }, [data, agentFilter])

  const uniqueAgents = useMemo(() => {
    if (!data?.decisions) return []
    return [...new Set(data.decisions.map((d) => d.selected_agent))]
  }, [data])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        Loading routing analytics...
      </div>
    )
  }

  if (error || !data) {
    return <ErrorState message={error || 'Failed to load routing data'} onRetry={refetch} />
  }

  const share = (method: RouteMethod) =>
    data.total_decisions
      ? `${(((data.method_counts[method] ?? 0) / data.total_decisions) * 100).toFixed(0)}%`
      : '—'

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RouteIcon className="h-5 w-5 text-subtle-foreground" />
          <h1 className="m-0 text-[1.375rem] font-semibold tracking-tight text-foreground">
            Routing Analytics
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-border overflow-hidden">
            {(Object.keys(RANGE_HOURS) as (keyof typeof RANGE_HOURS)[]).map((range) => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={cn(
                  'px-3 py-1.5 text-xs font-medium transition-colors',
                  timeRange === range
                    ? 'bg-brand-400/10 text-brand-400'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {range}
              </button>
            ))}
          </div>
          <button
            onClick={() => refetch()}
            className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            title="Refresh"
            aria-label="Refresh routing data"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Which agent answered each message, and how it was chosen. Kept since the server last
        started; chat text isn&apos;t stored.
      </p>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <SummaryCard
          label="Decisions"
          value={data.total_decisions.toLocaleString()}
          icon={RouteIcon}
        />
        <SummaryCard label="Chosen by user" value={share('requested')} icon={UserCheck} />
        <SummaryCard label="Keyword match" value={share('keyword')} icon={Search} />
        <SummaryCard
          label="Fallback"
          value={share('fallback')}
          icon={BarChart3}
          accent={(data.method_counts.fallback ?? 0) > 0 ? 'amber' : undefined}
        />
      </div>

      {/* Agents */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Agents</h2>
        {data.agent_stats.length === 0 ? (
          <p className="text-sm text-muted-foreground">No routing decisions in this period</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-start py-2 text-xs text-muted-foreground font-medium">
                    Agent
                  </th>
                  <th className="text-end py-2 text-xs text-muted-foreground font-medium">
                    Messages
                  </th>
                  <th className="text-end py-2 text-xs text-muted-foreground font-medium">
                    Fallback rate
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.agent_stats.map((agent) => (
                  <tr
                    key={agent.agent_key}
                    className="border-b border-border/50 hover:bg-surface-800/50 transition-colors"
                  >
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <Bot className="h-4 w-4 text-brand-400" />
                        <span className="font-medium text-foreground capitalize">
                          {agent.agent_key}
                        </span>
                      </div>
                    </td>
                    <td className="text-end py-3 text-muted-foreground">{agent.total_calls}</td>
                    <td className="text-end py-3">
                      <span
                        className={cn(
                          'text-xs',
                          agent.fallback_rate > 0.1 ? 'text-amber-400' : 'text-muted-foreground',
                        )}
                      >
                        {(agent.fallback_rate * 100).toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Recent decisions */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-foreground">Recent Decisions</h2>
          <div className="flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={agentFilter}
              onChange={(e) => setAgentFilter(e.target.value)}
              className="appearance-none bg-surface-800 border border-border rounded-lg px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
            >
              <option value="">All agents</option>
              {uniqueAgents.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
        </div>

        {filteredDecisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No routing decisions found</p>
        ) : (
          <div className="space-y-2">
            {filteredDecisions.map((d) => (
              <div
                key={d.id}
                className="rounded-lg border border-border p-3 hover:bg-surface-800/50 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    {d.message_preview && (
                      <p className="text-xs text-foreground truncate" dir="auto">
                        {d.message_preview}
                      </p>
                    )}
                    <div className="flex flex-wrap items-center gap-3 mt-1.5">
                      <span className="flex items-center gap-1 text-[10px] text-brand-400">
                        <Bot className="h-3 w-3" /> {d.selected_agent}
                      </span>
                      <span className="text-[10px] text-muted-foreground">{d.system_key}</span>
                      <span
                        className={cn(
                          'text-[10px] px-1.5 py-0.5 rounded',
                          d.method === 'fallback'
                            ? 'bg-amber-400/10 text-amber-400'
                            : 'bg-surface-700 text-muted-foreground',
                        )}
                      >
                        {METHOD_LABELS[d.method] ?? d.method}
                      </span>
                    </div>
                  </div>
                  <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                    {new Date(d.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {data.total_decisions > 50 && (
          <p className="text-xs text-muted-foreground text-center mt-4">
            Showing the latest 50 of {data.total_decisions} decisions
          </p>
        )}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Sub-components                                                      */
/* ------------------------------------------------------------------ */

function SummaryCard({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string
  value: string
  icon: typeof BarChart3
  accent?: 'green' | 'amber' | 'red'
}) {
  const accentColors = {
    green: 'text-green-400',
    amber: 'text-amber-400',
    red: 'text-red-400',
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-muted-foreground">{label}</span>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <div className={cn('text-2xl font-bold', accent ? accentColors[accent] : 'text-foreground')}>
        {value}
      </div>
    </div>
  )
}
