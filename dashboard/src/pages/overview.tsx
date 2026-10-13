import { useNavigate } from 'react-router-dom'
import { AlertCircle, Plug, ArrowRight, ShieldCheck } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { useAuth } from '@/hooks/use-auth'
import { Skeleton, SkeletonCard, SkeletonText } from '@/components/ui/skeleton'
import { VentureHealthCard } from '@/components/venture-health-card'
import { ActivityFeed, type ActivityEvent } from '@/components/activity-feed'
import type { Approval } from '@/components/approval-card'
import { TitleBlock } from '@/components/ui/title-block'
import { Panel } from '@/components/ui/panel'
import { Stat } from '@/components/ui/stat'
import { Button } from '@/components/ui/button'
import { Badge, StatusDot } from '@/components/ui/badge'
import { agentFigures, type AgentFigures } from '@/lib/dashboard-figures'
import { setupGate } from '@/lib/permissions'

interface DashboardData {
  ventures: Array<{
    key: string
    name: string
    agent_count: number
    skill_count: number
  }>
  venture_count: number
  recent_activity: ActivityEvent[]
  /** Configured agents (the headline); the sum of the ventures' agent counts. */
  agent_total?: number
  /** Configured agents by runtime state; one that never ran counts as idle. */
  agent_summary: Record<string, number>
}

export default function OverviewPage() {
  // Poll every 30s
  const { data, loading, error } = useApi<DashboardData>('/dashboard', 30000, 30000)
  const navigate = useNavigate()
  const { user } = useAuth()

  if (loading) {
    return (
      <div className="space-y-8" aria-busy="true" aria-label="Loading overview">
        <div>
          <Skeleton className="h-7 w-40 mb-2" />
          <Skeleton className="h-4 w-72" />
        </div>
        <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rz-panel p-4">
              <Skeleton className="h-3 w-16 mb-3" />
              <Skeleton className="h-8 w-12" />
            </div>
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <SkeletonCard />
          <div className="rz-panel p-6">
            <SkeletonText lines={8} />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-[10px] border border-red-400/30 bg-red-400/10 p-4 text-sm text-red-400"
      >
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{error}</span>
      </div>
    )
  }

  if (!data) return null

  const figures = agentFigures(data)
  const setupBlocked = setupGate(user)

  return (
    <div className="mx-auto max-w-[1240px]">
      <TitleBlock
        title="Overview"
        description="What is waiting for you, and what your agents have been doing."
      />

      {/* First-run banner */}
      {data.venture_count === 0 && figures.total === 0 && (
        <div className="rz-panel mb-6 flex flex-wrap items-center justify-between gap-4 p-5 fx-animated-border">
          <div>
            <div className="mb-1 flex items-center gap-2">
              <Plug className="h-5 w-5 text-brand-400" />
              <h2 className="m-0 text-[15px] font-semibold text-foreground">
                Welcome to RealizeOS
              </h2>
            </div>
            <p className="m-0 text-sm text-muted-foreground">
              {setupBlocked ??
                'Start by connecting your LLM providers and integrations, then create your first venture.'}
            </p>
          </div>
          {!setupBlocked && (
            <Button variant="primary" onClick={() => navigate('/setup')}>
              Set up connections
              <ArrowRight className="rtl:rotate-180" />
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex min-w-0 flex-col gap-6">
          <HeldForYou />

          <OverviewFigures ventureCount={data.venture_count} figures={figures} />

          {/* Ventures */}
          <section aria-labelledby="ov-ventures">
            <h2 id="ov-ventures" className="mb-3 text-[15px] font-semibold text-foreground">
              Ventures
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data.ventures.map((v) => (
                <VentureHealthCard
                  key={v.key}
                  name={v.name}
                  ventureKey={v.key}
                  agentCount={v.agent_count}
                  skillCount={v.skill_count}
                  onClick={() => navigate(`/ventures/${v.key}`, { viewTransition: true })}
                />
              ))}
              {data.ventures.length === 0 && (
                <p className="col-span-full m-0 text-sm text-muted-foreground">
                  No ventures configured. Use <code>python cli.py venture create --key my-biz</code>{' '}
                  to create one.
                </p>
              )}
            </div>
          </section>
        </div>

        <div className="flex min-w-0 flex-col gap-6">
          <SecurityPostureWidget />
          <Panel title="Recent activity" flush>
            <ActivityFeed events={data.recent_activity} maxItems={20} />
          </Panel>
        </div>
      </div>
    </div>
  )
}

/**
 * The headline figures. "Agents" counts configured agents (as the venture
 * cards do), not runtime-state rows; running and errors come from runtime state.
 */
export function OverviewFigures({
  ventureCount,
  figures,
}: {
  ventureCount: number
  figures: AgentFigures
}) {
  return (
    <div className="rz-panel grid grid-cols-2 gap-6 p-5 sm:grid-cols-4">
      <Stat label="Ventures" value={ventureCount} />
      <Stat label="Agents" value={figures.total} />
      <Stat
        label={
          <span className="inline-flex items-center gap-1.5">
            Running {figures.running > 0 && <StatusDot state="agent" live />}
          </span>
        }
        value={figures.running}
      />
      <Stat
        label={
          <span className="inline-flex items-center gap-1.5">
            Errors {figures.errors > 0 && <StatusDot state="error" />}
          </span>
        }
        value={figures.errors}
      />
    </div>
  )
}

/** The first thing a person sees: what is held for their decision. */
function HeldForYou() {
  const navigate = useNavigate()
  const { data, loading } = useApi<{ approvals: Approval[] }>('/approvals?status=pending')
  const held = (data?.approvals ?? []).filter((a) => a.status === 'pending')
  if (loading) return null

  return (
    <Panel
      held={held.length > 0}
      title={
        <span className="inline-flex items-center gap-2">
          Held for you
          {held.length > 0 && <Badge tone="accent">{held.length}</Badge>}
        </span>
      }
      actions={
        held.length > 0 ? (
          <Button size="sm" onClick={() => navigate('/approvals', { viewTransition: true })}>
            Review
            <ArrowRight className="rtl:rotate-180" />
          </Button>
        ) : undefined
      }
      flush
    >
      {held.length === 0 ? (
        <p className="m-0 flex items-center gap-2 px-4 py-4 text-sm text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-emerald-400" />
          Nothing is waiting for you. Agents will hold anything that touches money, contracts or
          people.
        </p>
      ) : (
        <ul className="m-0 list-none divide-y divide-border p-0">
          {held.slice(0, 4).map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-4 py-2.5 ps-5 text-[13px]">
              <span className="rz-avatar rz-avatar--agent rz-avatar--sm" aria-hidden>
                {a.agent_key.slice(0, 2).toUpperCase()}
              </span>
              <span className="min-w-0 flex-1 truncate text-foreground">
                {(a.action_name || a.action_type).replace(/_/g, ' ')}
                <span className="ms-2 text-subtle-foreground">
                  {a.agent_key} · {a.venture_key}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

interface SecurityStatusData {
  scan: { passed: number; warnings: number; critical: number; total: number } | null
}

function SecurityPostureWidget() {
  const { data } = useApi<SecurityStatusData>('/security/status')
  const scan = data?.scan

  if (!scan) return null

  const score = scan.total > 0 ? Math.round((scan.passed / scan.total) * 100) : 0
  const tone = scan.critical > 0 ? 'error' : scan.warnings > 2 ? 'review' : 'active'

  return (
    <Panel
      title={
        <span className="inline-flex items-center gap-2">
          <StatusDot state={tone} /> Security posture
        </span>
      }
    >
      <Stat label={`${scan.passed} of ${scan.total} checks passed`} value={score} unit="%" />
      <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
        <span>
          <span className="font-medium text-emerald-400">{scan.passed}</span> passed
        </span>
        <span>
          <span className="font-medium text-amber-400">{scan.warnings}</span> warnings
        </span>
        <span>
          <span className="font-medium text-red-400">{scan.critical}</span> critical
        </span>
      </div>
    </Panel>
  )
}
