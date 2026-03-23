import { useState, useMemo } from 'react'
import {
  Route as RouteIcon,
  BarChart3,
  Clock,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  Bot,
  Zap,
  Filter,
  RefreshCw,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface RoutingDecision {
  id: string
  timestamp: string
  venture_key: string
  user_message: string
  selected_agent: string
  confidence: number
  latency_ms: number
  model_used: string
  fallback_used: boolean
}

interface AgentStat {
  agent_key: string
  total_calls: number
  avg_confidence: number
  avg_latency_ms: number
  fallback_rate: number
}

interface ModelStat {
  model: string
  calls: number
  avg_latency_ms: number
  error_rate: number
}

interface RoutingData {
  decisions: RoutingDecision[]
  agent_stats: AgentStat[]
  model_stats: ModelStat[]
  total_decisions: number
  avg_latency_ms: number
  avg_confidence: number
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

export default function RoutingPage() {
  const { data: rawData, loading, error, refetch } = useApi<RoutingData>('/routing/analytics')
  const [timeRange, setTimeRange] = useState<'1h' | '24h' | '7d' | '30d'>('24h')
  const [agentFilter, setAgentFilter] = useState<string>('')

  // Normalize data with safe defaults to prevent crashes
  const data = useMemo<RoutingData | null>(() => {
    if (!rawData) return null
    return {
      decisions: rawData.decisions ?? [],
      agent_stats: rawData.agent_stats ?? [],
      model_stats: rawData.model_stats ?? [],
      total_decisions: rawData.total_decisions ?? 0,
      avg_latency_ms: rawData.avg_latency_ms ?? 0,
      avg_confidence: rawData.avg_confidence ?? 0,
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
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading routing analytics...</div>
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load routing data
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <RouteIcon className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Routing Analytics</h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-border overflow-hidden">
            {(['1h', '24h', '7d', '30d'] as const).map((range) => (
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
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <SummaryCard
          label="Total Decisions"
          value={data.total_decisions.toLocaleString()}
          icon={RouteIcon}
        />
        <SummaryCard
          label="Avg Confidence"
          value={`${(data.avg_confidence * 100).toFixed(1)}%`}
          icon={TrendingUp}
          accent={data.avg_confidence >= 0.8 ? 'green' : data.avg_confidence >= 0.6 ? 'amber' : 'red'}
        />
        <SummaryCard
          label="Avg Latency"
          value={`${data.avg_latency_ms.toFixed(0)}ms`}
          icon={Clock}
          accent={data.avg_latency_ms <= 500 ? 'green' : data.avg_latency_ms <= 1500 ? 'amber' : 'red'}
        />
        <SummaryCard
          label="Active Models"
          value={`${data.model_stats.length}`}
          icon={Bot}
        />
      </div>

      {/* Agent performance */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Agent Performance</h2>
        {data.agent_stats.length === 0 ? (
          <p className="text-sm text-muted-foreground">No agent data available</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 text-xs text-muted-foreground font-medium">Agent</th>
                  <th className="text-right py-2 text-xs text-muted-foreground font-medium">Calls</th>
                  <th className="text-right py-2 text-xs text-muted-foreground font-medium">Avg Confidence</th>
                  <th className="text-right py-2 text-xs text-muted-foreground font-medium">Avg Latency</th>
                  <th className="text-right py-2 text-xs text-muted-foreground font-medium">Fallback Rate</th>
                </tr>
              </thead>
              <tbody>
                {data.agent_stats.map((agent) => (
                  <tr key={agent.agent_key} className="border-b border-border/50 hover:bg-surface-800/50 transition-colors">
                    <td className="py-3">
                      <div className="flex items-center gap-2">
                        <Bot className="h-4 w-4 text-brand-400" />
                        <span className="font-medium text-foreground capitalize">{agent.agent_key}</span>
                      </div>
                    </td>
                    <td className="text-right py-3 text-muted-foreground">{agent.total_calls}</td>
                    <td className="text-right py-3">
                      <ConfidenceBadge value={agent.avg_confidence} />
                    </td>
                    <td className="text-right py-3">
                      <LatencyBadge value={agent.avg_latency_ms} />
                    </td>
                    <td className="text-right py-3">
                      <span className={cn(
                        'text-xs',
                        agent.fallback_rate > 0.1 ? 'text-amber-400' : 'text-muted-foreground',
                      )}>
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

      {/* Model stats */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Model Usage</h2>
        <div className="grid gap-3 md:grid-cols-3">
          {data.model_stats.map((model) => (
            <div key={model.model} className="rounded-lg border border-border p-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground">{model.model}</span>
                <span className="text-xs text-muted-foreground">{model.calls} calls</span>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className="text-muted-foreground">
                  <Clock className="h-3 w-3 inline mr-1" />
                  {model.avg_latency_ms.toFixed(0)}ms
                </span>
                <span className={cn(
                  model.error_rate > 0.05 ? 'text-red-400' : 'text-muted-foreground',
                )}>
                  {model.error_rate > 0 && <AlertCircle className="h-3 w-3 inline mr-1" />}
                  {(model.error_rate * 100).toFixed(1)}% errors
                </span>
              </div>
              {/* Usage bar */}
              <div className="mt-3 h-1.5 rounded-full bg-surface-700 overflow-hidden">
                <div
                  className="h-full rounded-full bg-brand-400 transition-all"
                  style={{
                    width: `${Math.min(100, (model.calls / Math.max(1, ...data.model_stats.map((m) => m.calls))) * 100)}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
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
                <option key={a} value={a}>{a}</option>
              ))}
            </select>
          </div>
        </div>

        {filteredDecisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No routing decisions found</p>
        ) : (
          <div className="space-y-2">
            {filteredDecisions.map((d) => (
              <div key={d.id} className="rounded-lg border border-border p-3 hover:bg-surface-800/50 transition-colors">
                <div className="flex items-start gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-foreground truncate">{d.user_message}</p>
                    <div className="flex flex-wrap items-center gap-3 mt-1.5">
                      <span className="flex items-center gap-1 text-[10px] text-brand-400">
                        <Bot className="h-3 w-3" /> {d.selected_agent}
                      </span>
                      <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                        <Zap className="h-3 w-3" /> {d.model_used}
                      </span>
                      <ConfidenceBadge value={d.confidence} />
                      <LatencyBadge value={d.latency_ms} />
                      {d.fallback_used && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400">
                          fallback
                        </span>
                      )}
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
            Showing 50 of {data.total_decisions} decisions
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

function ConfidenceBadge({ value }: { value: number }) {
  const pct = (value * 100).toFixed(0)
  const color = value >= 0.8 ? 'text-green-400' : value >= 0.6 ? 'text-amber-400' : 'text-red-400'
  const TrendIcon = value >= 0.8 ? TrendingUp : value >= 0.6 ? Minus : TrendingDown

  return (
    <span className={cn('flex items-center gap-0.5 text-[10px]', color)}>
      <TrendIcon className="h-3 w-3" /> {pct}%
    </span>
  )
}

function LatencyBadge({ value }: { value: number }) {
  const color = value <= 500 ? 'text-green-400' : value <= 1500 ? 'text-amber-400' : 'text-red-400'

  return (
    <span className={cn('flex items-center gap-0.5 text-[10px]', color)}>
      <Clock className="h-3 w-3" /> {value.toFixed(0)}ms
    </span>
  )
}
