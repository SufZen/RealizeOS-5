import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ChevronLeft, Bot, AlertCircle, Pause, Play, Clock, Save } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { AgentStatusBadge, type AgentStatus } from '@/components/agent-status-badge'
import { ActivityFeed, type ActivityEvent } from '@/components/activity-feed'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface AgentData {
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
  const navigate = useNavigate()
  const { data, loading, error, refetch } = useApi<AgentData>(
    `/ventures/${ventureKey}/agents/${agentKey}`,
  )

  async function handlePause() {
    await api.post(`/ventures/${ventureKey}/agents/${agentKey}/pause`)
    refetch()
  }

  async function handleResume() {
    await api.post(`/ventures/${ventureKey}/agents/${agentKey}/resume`)
    refetch()
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading agent...</div>
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

  const isPaused = data.status === 'paused'
  const isError = data.status === 'error'

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <button
          onClick={() => navigate(`/ventures/${ventureKey}`)}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-2 transition-colors"
        >
          <ChevronLeft className="h-3 w-3" />
          Back to {ventureKey}
        </button>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Bot className="h-6 w-6 text-brand-400" />
            <div>
              <h1 className="text-2xl font-bold text-foreground">{data.key}</h1>
              <span className="text-xs text-muted-foreground font-mono">{data.definition_path}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <AgentStatusBadge status={data.status} />
            {isPaused ? (
              <button
                onClick={handleResume}
                className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition-colors"
              >
                <Play className="h-3.5 w-3.5" />
                Resume
              </button>
            ) : (
              <button
                onClick={handlePause}
                className="flex items-center gap-1.5 rounded-lg bg-surface-700 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                <Pause className="h-3.5 w-3.5" />
                Pause
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Status details */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
            {data.schedule_cron || (data.schedule_interval_sec ? `Every ${data.schedule_interval_sec}s` : 'None')}
          </p>
        </div>
        <div className="rounded-xl border border-border bg-card p-4">
          <span className="text-xs text-muted-foreground">Next Run</span>
          <p className="mt-1 text-sm text-foreground">
            {data.next_run_at ? <NextRunCountdown target={data.next_run_at} /> : 'Not scheduled'}
          </p>
        </div>
      </div>

      {/* Schedule editor */}
      <ScheduleEditor
        ventureKey={data.venture_key}
        agentKey={data.key}
        currentCron={data.schedule_cron}
        currentInterval={data.schedule_interval_sec}
        onSaved={refetch}
      />

      {/* Error display */}
      {isError && data.last_error && (
        <div className="rounded-xl border border-red-400/30 bg-red-400/5 p-4">
          <span className="text-xs font-medium text-red-400">Last Error</span>
          <p className="mt-1 text-sm text-red-300 font-mono whitespace-pre-wrap">{data.last_error}</p>
        </div>
      )}

      {/* Agent definition */}
      {data.definition && (
        <section>
          <h2 className="text-lg font-semibold text-foreground mb-3">Configuration</h2>
          <div className="rounded-xl border border-border bg-card p-4">
            <pre
              className={cn(
                'text-sm text-muted-foreground whitespace-pre-wrap font-mono',
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
        <h2 className="text-lg font-semibold text-foreground mb-3">
          Recent Activity ({data.recent_activity.length})
        </h2>
        <div className="rounded-xl border border-border bg-card">
          <ActivityFeed events={data.recent_activity} maxItems={20} />
        </div>
      </section>
    </div>
  )
}
