import { useNavigate } from 'react-router-dom'
import { LayoutDashboard, Users, Briefcase, AlertCircle, Plug, ArrowRight, ShieldCheck } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { Skeleton, SkeletonCard, SkeletonText } from '@/components/ui/skeleton'
import { VentureHealthCard } from '@/components/venture-health-card'
import { ActivityFeed, type ActivityEvent } from '@/components/activity-feed'

interface DashboardData {
  ventures: Array<{
    key: string
    name: string
    agent_count: number
    skill_count: number
  }>
  venture_count: number
  recent_activity: ActivityEvent[]
  agent_summary: Record<string, number>
}

function StatCard({ label, value, icon: Icon }: { label: string; value: number; icon: typeof Users }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </div>
      <p className="mt-2 text-2xl font-bold text-foreground">{value}</p>
    </div>
  )
}

export default function OverviewPage() {
  // Pool every 30s
  const { data, loading, error } = useApi<DashboardData>('/dashboard', 30000, 30000)
  const navigate = useNavigate()

  if (loading) {
    return (
      <div className="space-y-8 animate-in fade-in duration-500">
        <div>
          <Skeleton className="h-8 w-48 mb-2" />
          <Skeleton className="h-4 w-64" />
        </div>

        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-border bg-card p-4">
              <div className="flex items-center justify-between mb-2">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-4 w-4 rounded-full" />
              </div>
              <Skeleton className="h-8 w-12" />
            </div>
          ))}
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-4">
            <Skeleton className="h-6 w-32" />
            <div className="grid gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          </div>
          <div className="space-y-4">
            <Skeleton className="h-6 w-32" />
            <div className="rounded-xl border border-border bg-card p-6">
              <SkeletonText lines={10} />
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      </div>
    )
  }

  if (!data) return null

  const totalAgents = Object.values(data.agent_summary).reduce((a, b) => a + b, 0)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <LayoutDashboard className="h-6 w-6 text-brand-400" />
        <h1 className="text-2xl font-bold text-foreground">Overview</h1>
      </div>

      {/* First-run banner */}
      {data.venture_count === 0 && totalAgents === 0 && (
        <div className="rounded-xl border border-brand-400/30 bg-brand-400/5 p-5 flex items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Plug className="h-5 w-5 text-brand-400" />
              <h2 className="text-sm font-semibold text-brand-400">Welcome to RealizeOS</h2>
            </div>
            <p className="text-xs text-muted-foreground">
              Start by connecting your LLM providers and integrations, then create your first venture.
            </p>
          </div>
          <button
            onClick={() => navigate('/setup')}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 font-medium transition-colors shrink-0"
          >
            Setup Connections
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Ventures" value={data.venture_count} icon={Briefcase} />
        <StatCard label="Total Agents" value={totalAgents} icon={Users} />
        <StatCard
          label="Running"
          value={data.agent_summary.running || 0}
          icon={Users}
        />
        <StatCard
          label="Errors"
          value={data.agent_summary.error || 0}
          icon={AlertCircle}
        />
      </div>

      {/* Security Posture */}
      <SecurityPostureWidget />

      {/* Ventures */}
      <section>
        <h2 className="text-lg font-semibold text-foreground mb-3">Ventures</h2>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {data.ventures.map((v) => (
            <VentureHealthCard
              key={v.key}
              name={v.name}
              ventureKey={v.key}
              agentCount={v.agent_count}
              skillCount={v.skill_count}
              onClick={() => navigate(`/ventures/${v.key}`)}
            />
          ))}
          {data.ventures.length === 0 && (
            <p className="text-muted-foreground text-sm col-span-full">
              No ventures configured. Use <code>python cli.py venture create --key my-biz</code> to create one.
            </p>
          )}
        </div>
      </section>

      {/* Recent Activity */}
      <section>
        <h2 className="text-lg font-semibold text-foreground mb-3">Recent Activity</h2>
        <div className="rounded-xl border border-border bg-card">
          <ActivityFeed events={data.recent_activity} maxItems={20} />
        </div>
      </section>
    </div>
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
  const color = scan.critical > 0 ? 'text-red-400' : scan.warnings > 2 ? 'text-amber-400' : 'text-emerald-400'
  const bgColor = scan.critical > 0 ? 'border-red-400/20' : scan.warnings > 2 ? 'border-amber-400/20' : 'border-emerald-400/20'

  return (
    <div className={`rounded-xl border ${bgColor} bg-card p-4`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className={`h-5 w-5 ${color}`} />
          <span className="text-sm font-semibold text-foreground">Security Posture</span>
        </div>
        <span className={`text-2xl font-bold ${color}`}>{score}%</span>
      </div>
      <div className="flex gap-4 mt-2 text-xs text-muted-foreground">
        <span><span className="text-emerald-400 font-medium">{scan.passed}</span> passed</span>
        <span><span className="text-amber-400 font-medium">{scan.warnings}</span> warnings</span>
        <span><span className="text-red-400 font-medium">{scan.critical}</span> critical</span>
        <span className="ml-auto">of {scan.total} checks</span>
      </div>
    </div>
  )
}
