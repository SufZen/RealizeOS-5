import { useState, useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ChevronLeft, Bot, AlertCircle, Pause, Play, Clock, Save, Info } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { useAuth } from '@/hooks/use-auth'
import { AgentStatusBadge, type AgentStatus } from '@/components/agent-status-badge'
import { ActivityFeed, type ActivityEvent } from '@/components/activity-feed'
import { useToast } from '@/components/ui/toast'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { agentControlsGate, type Gate } from '@/lib/permissions'

export interface AgentData {
  key: string
  venture_key: string
  definition_path: string
  definition: string
  status: AgentStatus
  last_run_at: string | null
  last_error: string | null
  schedule_cron: string | null
  schedule_interval_sec: number | null
  next_run_at: string | null
  recent_activity: ActivityEvent[]
}

function NextRunCountdown({ target }: { target: string }) {
  const [label, setLabel] = useState('')

  useEffect(() => {
    function update() {
      const diff = new Date(target).getTime() - Date.now()
      if (diff <= 0) {
        setLabel('Now')
        return
      }
      const mins = Math.floor(diff / 60000)
      const secs = Math.floor((diff % 60000) / 1000)
      setLabel(mins > 0 ? `${mins}m ${secs}s` : `${secs}s`)
    }
    update()
    const id = setInterval(update, 1000)
    return () => clearInterval(id)
  }, [target])

  return (
    <span className="inline-flex items-center gap-1">
      <Clock className="h-3 w-3 text-brand-400" />
      {label}
    </span>
  )
}

function ScheduleEditor({
  ventureKey,
  agentKey,
  currentCron,
  currentInterval,
  onSaved,
}: {
  ventureKey: string
  agentKey: string
  currentCron: string | null
  currentInterval: number | null
  onSaved: () => void
}) {
  const [mode, setMode] = useState<'interval' | 'cron'>(currentCron ? 'cron' : 'interval')
  const [interval, setInterval] = useState(String(currentInterval || ''))
  const [cron, setCron] = useState(currentCron || '')
  const [saving, setSaving] = useState(false)

  async function handleSave() {
    setSaving(true)
    try {
      const body =
        mode === 'cron'
          ? { schedule_cron: cron }
          : { schedule_interval_sec: parseInt(interval, 10) || 0 }
      await api.put(`/ventures/${ventureKey}/agents/${agentKey}/schedule`, body)
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  async function handleClear() {
    setSaving(true)
    try {
      await api.delete(`/ventures/${ventureKey}/agents/${agentKey}/schedule`)
      setInterval('')
      setCron('')
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <h3 className="text-sm font-semibold text-foreground mb-3">Schedule Configuration</h3>
      <div className="flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Type</label>
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as 'interval' | 'cron')}
            className="rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground"
          >
            <option value="interval">Interval (seconds)</option>
            <option value="cron">Cron expression</option>
          </select>
        </div>
        {mode === 'interval' ? (
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Seconds</label>
            <input
              type="number"
              min="60"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              placeholder="300"
              className="w-28 rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground"
            />
          </div>
        ) : (
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Cron</label>
            <input
              type="text"
              value={cron}
              onChange={(e) => setCron(e.target.value)}
              placeholder="*/5 * * * *"
              className="w-40 rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground font-mono"
            />
          </div>
        )}
        <button
          onClick={handleSave}
          disabled={saving}
          className={cn(
            'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
            'bg-brand-400/10 text-brand-400 hover:bg-brand-400/20',
          )}
        >
          <Save className="h-3.5 w-3.5" />
          {saving ? 'Saving...' : 'Save'}
        </button>
        {(currentCron || currentInterval) && (
          <button
            onClick={handleClear}
            disabled={saving}
            className="rounded-lg px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear schedule
          </button>
        )}
      </div>
    </section>
  )
}

export default function AgentDetailPage() {
  const { key: ventureKey, id: agentKey } = useParams<{ key: string; id: string }>()
  const { user } = useAuth()
  const toast = useToast()
  const { data, loading, error, refetch } = useApi<AgentData>(
    `/ventures/${ventureKey}/agents/${agentKey}`,
  )

  async function change(verb: 'pause' | 'resume') {
    try {
      await api.post(`/ventures/${ventureKey}/agents/${agentKey}/${verb}`)
    } catch (err) {
      // The server decides every change; a refusal is said, not swallowed.
      toast.error(err instanceof Error && err.message ? err.message : `Couldn’t ${verb} the agent`)
    } finally {
      refetch()
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-muted-foreground">
        Loading agent...
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

  return (
    <AgentDetailView
      data={data}
      ventureKey={ventureKey ?? data.venture_key}
      gate={agentControlsGate(user)}
      onPause={() => change('pause')}
      onResume={() => change('resume')}
      onScheduleSaved={refetch}
    />
  )
}

/**
 * One agent: status, schedule, definition and recent activity. `gate` is set
 * when the person's role can't change agents (`system:write`): pause, resume
 * and the schedule editor are left out, and one line says why.
 */
export function AgentDetailView({
  data,
  ventureKey,
  gate,
  onPause,
  onResume,
  onScheduleSaved,
}: {
  data: AgentData
  ventureKey: string
  gate: Gate
  onPause: () => void
  onResume: () => void
  onScheduleSaved: () => void
}) {
  const isPaused = data.status === 'paused'
  const isError = data.status === 'error'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link
          to={`/ventures/${ventureKey}`}
          viewTransition
          className="mb-2 inline-flex items-center gap-1 text-xs text-muted-foreground no-underline transition-colors hover:text-foreground"
        >
          <ChevronLeft className="h-3 w-3 rtl:rotate-180" aria-hidden />
          <span dir="auto">
            Back to <bdi>{ventureKey}</bdi>
          </span>
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <Bot className="h-5 w-5 shrink-0 text-subtle-foreground" aria-hidden />
            <div className="min-w-0">
              <h1 className="m-0 text-[1.375rem] font-semibold tracking-tight text-foreground">
                {data.key}
              </h1>
              <span dir="ltr" className="block truncate font-mono text-xs text-muted-foreground">
                {data.definition_path}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <AgentStatusBadge status={data.status} />
            {!gate &&
              (isPaused ? (
                <button
                  onClick={onResume}
                  className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20"
                >
                  <Play className="h-3.5 w-3.5" aria-hidden />
                  Resume
                </button>
              ) : (
                <button
                  onClick={onPause}
                  className="flex items-center gap-1.5 rounded-lg bg-surface-700 px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
                >
                  <Pause className="h-3.5 w-3.5" aria-hidden />
                  Pause
                </button>
              ))}
          </div>
        </div>
        {gate && (
          <p
            data-gate="agent"
            className="m-0 mt-3 flex items-start gap-2 text-[13px] text-muted-foreground"
          >
            <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" aria-hidden />
            <span dir="auto">{gate}</span>
          </p>
        )}
      </div>

      {/* Status details */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-border bg-card p-4">
          <span className="text-xs text-muted-foreground">Status</span>
          <div className="mt-1">
            <AgentStatusBadge status={data.status} className="text-sm" />
          </div>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <span className="text-xs text-muted-foreground">Last Run</span>
          <p className="mt-1 text-sm text-foreground">
            {data.last_run_at ? new Date(data.last_run_at).toLocaleString() : 'Never'}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <span className="text-xs text-muted-foreground">Schedule</span>
          <p className="mt-1 text-sm text-foreground">
            {data.schedule_cron ||
              (data.schedule_interval_sec ? `Every ${data.schedule_interval_sec}s` : 'None')}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <span className="text-xs text-muted-foreground">Next Run</span>
          <p className="mt-1 text-sm text-foreground">
            {data.next_run_at ? <NextRunCountdown target={data.next_run_at} /> : 'Not scheduled'}
          </p>
        </div>
      </div>

      {/* Schedule editor: only for a role that may change agents */}
      {!gate && (
        <ScheduleEditor
          ventureKey={data.venture_key}
          agentKey={data.key}
          currentCron={data.schedule_cron}
          currentInterval={data.schedule_interval_sec}
          onSaved={onScheduleSaved}
        />
      )}

      {/* Error display */}
      {isError && data.last_error && (
        <div className="rounded-xl border border-red-400/30 bg-red-400/5 p-4">
          <span className="text-xs font-medium text-red-400">Last Error</span>
          <p className="mt-1 whitespace-pre-wrap font-mono text-sm text-red-300">
            {data.last_error}
          </p>
        </div>
      )}

      {/* Agent definition */}
      {data.definition && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-foreground">Configuration</h2>
          <div className="rounded-xl border border-border bg-card p-4">
            <pre
              dir="auto"
              className={cn(
                'whitespace-pre-wrap font-mono text-sm text-muted-foreground',
                'max-h-64 overflow-y-auto',
              )}
            >
              {data.definition}
            </pre>
          </div>
        </section>
      )}

      {/* Action history */}
      <section>
        <h2 className="mb-3 text-lg font-semibold text-foreground">
          Recent Activity ({data.recent_activity.length})
        </h2>
        <div className="rounded-xl border border-border bg-card">
          <ActivityFeed events={data.recent_activity} maxItems={20} />
        </div>
      </section>
    </div>
  )
}
