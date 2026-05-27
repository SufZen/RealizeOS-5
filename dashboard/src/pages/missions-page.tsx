import { useState } from 'react'
import {
  Target,
  Play,
  Pause,
  XCircle,
  CheckCircle2,
  Clock,
  ChevronRight,
  RefreshCw,
  AlertTriangle,
  Loader2,
  Filter,
  BarChart3,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { cn } from '@/lib/utils'

/* ─── Types ──────────────────────────────────────────────────────── */

interface MissionStep {
  step_id: string
  description: string
  runtime: string
  status: string
  cost_eur: number
  duration_sec: number | null
}

interface Mission {
  mission_id: string
  title: string
  goal: string
  venture: string
  state: string
  progress: number
  plan: MissionStep[]
  budget_eur: number | null
  cost_consumed_eur: number
  created_at: string
  started_at: string | null
  completed_at: string | null
  outcome_summary: string
}

interface MissionsResponse {
  missions: Mission[]
  count: number
}

/* ─── State badge ────────────────────────────────────────────────── */

const stateConfig: Record<string, { icon: typeof Target; color: string; label: string }> = {
  proposed: { icon: Target, color: 'text-blue-400 bg-blue-400/10', label: 'Proposed' },
  planned: { icon: Clock, color: 'text-violet-400 bg-violet-400/10', label: 'Planned' },
  'in-progress': { icon: Loader2, color: 'text-amber-400 bg-amber-400/10', label: 'In Progress' },
  paused: { icon: Pause, color: 'text-gray-400 bg-gray-400/10', label: 'Paused' },
  'awaiting-approval': {
    icon: AlertTriangle,
    color: 'text-orange-400 bg-orange-400/10',
    label: 'Awaiting Approval',
  },
  completed: {
    icon: CheckCircle2,
    color: 'text-emerald-400 bg-emerald-400/10',
    label: 'Completed',
  },
  failed: { icon: XCircle, color: 'text-red-400 bg-red-400/10', label: 'Failed' },
  cancelled: { icon: XCircle, color: 'text-gray-500 bg-gray-500/10', label: 'Cancelled' },
}
const fallbackStateConfig = stateConfig.proposed!

function StateBadge({ state }: { state: string }) {
  const cfg = stateConfig[state] ?? fallbackStateConfig
  const Icon = cfg.icon
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium',
        cfg.color,
      )}
    >
      <Icon className={cn('h-3 w-3', state === 'in-progress' && 'animate-spin')} />
      {cfg.label}
    </span>
  )
}

/* ─── Progress bar ───────────────────────────────────────────────── */

function ProgressBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn('h-1.5 rounded-full bg-surface-700 overflow-hidden', className)}>
      <div
        className="h-full rounded-full bg-gradient-to-r from-brand-400 to-brand-600 transition-all duration-500"
        style={{ width: `${Math.min(value * 100, 100)}%` }}
      />
    </div>
  )
}

/* ─── Step list ──────────────────────────────────────────────────── */

function StepList({ steps }: { steps: MissionStep[] }) {
  if (!steps?.length) return null

  const stepStatusIcon: Record<string, { icon: typeof CheckCircle2; color: string }> = {
    succeeded: { icon: CheckCircle2, color: 'text-emerald-400' },
    failed: { icon: XCircle, color: 'text-red-400' },
    'in-progress': { icon: Loader2, color: 'text-amber-400' },
    pending: { icon: Clock, color: 'text-muted-foreground' },
    skipped: { icon: XCircle, color: 'text-gray-500' },
  }
  const fallbackStepStatusIcon = stepStatusIcon.pending!

  return (
    <div className="space-y-1">
      {steps.map((step) => {
        const cfg = stepStatusIcon[step.status] ?? fallbackStepStatusIcon
        const Icon = cfg.icon
        return (
          <div key={step.step_id} className="flex items-center gap-2 text-xs">
            <Icon
              className={cn(
                'h-3.5 w-3.5 flex-shrink-0',
                cfg.color,
                step.status === 'in-progress' && 'animate-spin',
              )}
            />
            <span className="text-foreground truncate flex-1">{step.description}</span>
            <span className="text-muted-foreground font-mono">{step.runtime}</span>
            {step.cost_eur > 0 && (
              <span className="text-muted-foreground font-mono">€{step.cost_eur.toFixed(3)}</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

/* ─── Mission card ───────────────────────────────────────────────── */

function MissionCard({ mission }: { mission: Mission }) {
  const [expanded, setExpanded] = useState(false)
  const hasSteps = mission.plan && mission.plan.length > 0
  const completedSteps =
    mission.plan?.filter((s) => ['succeeded', 'failed', 'skipped'].includes(s.status)).length || 0

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card p-4 transition-all duration-200',
        'hover:border-brand-400/30 hover:shadow-lg hover:shadow-brand-400/5',
        expanded && 'ring-1 ring-brand-400/20',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-foreground truncate">{mission.title}</h3>
            <StateBadge state={mission.state} />
          </div>
          <p className="text-xs text-muted-foreground line-clamp-2 mb-2">{mission.goal}</p>

          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {mission.venture && (
              <span className="bg-surface-700 px-2 py-0.5 rounded">{mission.venture}</span>
            )}
            {hasSteps && (
              <span>
                {completedSteps}/{mission.plan.length} steps
              </span>
            )}
            {mission.budget_eur != null && (
              <span className="font-mono">
                €{mission.cost_consumed_eur.toFixed(2)} / €{mission.budget_eur.toFixed(2)}
              </span>
            )}
            <span>{new Date(mission.created_at).toLocaleDateString()}</span>
          </div>
        </div>

        {hasSteps && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded-lg p-1.5 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            aria-label={expanded ? 'Collapse steps' : 'Expand steps'}
          >
            <ChevronRight className={cn('h-4 w-4 transition-transform', expanded && 'rotate-90')} />
          </button>
        )}
      </div>

      {/* Progress bar */}
      {hasSteps && mission.state === 'in-progress' && (
        <ProgressBar value={mission.progress} className="mt-3" />
      )}

      {/* Outcome summary */}
      {mission.outcome_summary && (
        <p className="mt-2 text-xs text-muted-foreground italic border-l-2 border-brand-400/30 pl-2">
          {mission.outcome_summary}
        </p>
      )}

      {/* Expanded step list */}
      {expanded && hasSteps && (
        <div className="mt-3 pt-3 border-t border-border">
          <StepList steps={mission.plan} />
        </div>
      )}
    </div>
  )
}

/* ─── Page ────────────────────────────────────────────────────────── */

export default function MissionsPage() {
  const [stateFilter, setStateFilter] = useState('')
  const [ventureFilter, setVentureFilter] = useState('')

  const params = new URLSearchParams()
  if (stateFilter) params.set('state', stateFilter)
  if (ventureFilter) params.set('venture', ventureFilter)

  const query = params.toString()
  const { data, loading, error, refetch } = useApi<MissionsResponse>(
    `/missions${query ? `?${query}` : ''}`,
    30000,
    10000,
  )

  const missions = data?.missions ?? []

  // Stats
  const totalMissions = missions.length
  const activeMissions = missions.filter((m) => ['in-progress', 'planned'].includes(m.state)).length
  const completedMissions = missions.filter((m) => m.state === 'completed').length
  const totalCost = missions.reduce((sum, m) => sum + m.cost_consumed_eur, 0)

  return (
    <div className="space-y-6 rz-animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Missions</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refetch}
            className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            aria-label="Refresh missions"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total', value: totalMissions, icon: Target, color: 'text-brand-400' },
          { label: 'Active', value: activeMissions, icon: Play, color: 'text-amber-400' },
          {
            label: 'Completed',
            value: completedMissions,
            icon: CheckCircle2,
            color: 'text-emerald-400',
          },
          {
            label: 'Cost',
            value: `€${totalCost.toFixed(3)}`,
            icon: BarChart3,
            color: 'text-violet-400',
          },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="rounded-xl border border-border bg-card p-3 fx-glass">
            <div className="flex items-center gap-2 mb-1">
              <Icon className={cn('h-4 w-4', color)} />
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
            <div className="text-lg font-bold text-foreground">{value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Filter className="h-3.5 w-3.5" />
          <span>Filter:</span>
        </div>
        <select
          value={stateFilter}
          onChange={(e) => setStateFilter(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground',
            'focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        >
          <option value="">All states</option>
          {Object.entries(stateConfig).map(([key, { label }]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Venture"
          value={ventureFilter}
          onChange={(e) => setVentureFilter(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground',
            'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        />
      </div>

      {/* Missions list */}
      <div className="space-y-3">
        {error && (
          <div className="rounded-xl border border-red-400/30 bg-red-400/10 p-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {loading && (
          <div className="rounded-xl border border-border bg-card p-8 text-center text-muted-foreground text-sm">
            Loading missions...
          </div>
        )}

        {!loading &&
          missions.map((mission) => <MissionCard key={mission.mission_id} mission={mission} />)}

        {missions.length === 0 && !loading && !error && (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Target className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
            <h3 className="text-sm font-medium text-foreground mb-1">No missions yet</h3>
            <p className="text-xs text-muted-foreground">
              Missions will appear here when agents start executing structured goals.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
