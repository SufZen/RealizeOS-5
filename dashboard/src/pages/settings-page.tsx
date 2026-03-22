import { useState } from 'react'
import { Settings, Shield, Cpu, Server, RefreshCw, Database, AlertCircle, Check, Brain, Search, Route, FileText, ShieldCheck, Loader2 } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Provider {
  name: string
  available: boolean
  models: string[]
}

interface SettingsData {
  features: Record<string, boolean>
  gates: Record<string, boolean>
  providers: Provider[]
  system_info: {
    python_version: string
    db_size_bytes: number
    kb_file_count: number
    config_path: string
  }
}

const FEATURE_LABELS: Record<string, string> = {
  activity_log: 'Activity Log — log all agent actions to SQLite',
  agent_lifecycle: 'Agent Lifecycle — track agent status (idle/running/paused/error)',
  heartbeats: 'Heartbeats — scheduled agent runs',
  approval_gates: 'Approval Gates — require human approval for consequential actions',
  review_pipeline: 'Review Pipeline — auto-route to reviewer agent',
  auto_memory: 'Auto Memory — log learnings after interactions',
  proactive_mode: 'Proactive Mode — include proactive layer in prompts',
  cross_system: 'Cross System — share context across all ventures',
}

const GATE_LABELS: Record<string, string> = {
  send_email: 'Send Email',
  publish_content: 'Publish Content',
  external_api: 'External API Calls',
  create_event: 'Create Calendar Events',
  high_cost_llm: 'High-Cost LLM Calls',
}

function Toggle({
  checked,
  onChange,
  disabled,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  disabled?: boolean
}) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors',
        checked ? 'bg-brand-400' : 'bg-surface-600',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform',
          checked ? 'translate-x-[18px]' : 'translate-x-[3px]',
        )}
      />
    </button>
  )
}

function StatusBanner({ message, type }: { message: string; type: 'success' | 'error' }) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 text-sm rounded-lg px-4 py-2',
        type === 'success' ? 'bg-green-400/10 text-green-400 border border-green-400/20' : 'bg-red-400/10 text-red-400 border border-red-400/20',
      )}
    >
      {type === 'success' ? <Check className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
      {message}
    </div>
  )
}

export default function SettingsPage() {
  const { data, loading, error, refetch } = useApi<SettingsData>('/settings')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading settings...</div>
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load settings
      </div>
    )
  }

  async function toggleFeature(key: string, value: boolean) {
    setSaving(true)
    setStatus(null)
    try {
      await api.put('/settings/features', { [key]: value })
      setStatus({ message: `Feature "${key}" ${value ? 'enabled' : 'disabled'}`, type: 'success' })
      refetch()
    } catch {
      setStatus({ message: `Failed to update feature "${key}"`, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function toggleGate(key: string, value: boolean) {
    setSaving(true)
    setStatus(null)
    try {
      await api.put('/settings/gates', { [key]: value })
      setStatus({ message: `Gate "${key}" ${value ? 'enabled' : 'disabled'}`, type: 'success' })
      refetch()
    } catch {
      setStatus({ message: `Failed to update gate "${key}"`, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function handleReindex() {
    setSaving(true)
    setStatus(null)
    try {
      const res = await api.post<{ files_indexed: number }>('/settings/reindex')
      setStatus({ message: `KB re-indexed: ${res.files_indexed} files`, type: 'success' })
      refetch()
    } catch {
      setStatus({ message: 'Re-index failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function handleReload() {
    setSaving(true)
    setStatus(null)
    try {
      await api.post('/systems/reload')
      setStatus({ message: 'Configuration reloaded', type: 'success' })
      refetch()
    } catch {
      setStatus({ message: 'Reload failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-foreground">Settings</h1>

      {status && <StatusBanner message={status.message} type={status.type} />}

      {/* Feature Flags */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Settings className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">Feature Flags</h2>
        </div>
        <div className="space-y-3">
          {Object.entries(FEATURE_LABELS).map(([key, label]) => (
            <div key={key} className="flex items-center justify-between gap-4">
              <span className="text-sm text-foreground">{label}</span>
              <Toggle
                checked={!!data.features[key]}
                onChange={(v) => toggleFeature(key, v)}
                disabled={saving}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Governance Gates */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Shield className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">Governance Gates</h2>
        </div>
        <p className="text-xs text-muted-foreground mb-4">Actions that require human approval before execution</p>
        <div className="space-y-3">
          {Object.entries(GATE_LABELS).map(([key, label]) => (
            <div key={key} className="flex items-center justify-between gap-4">
              <span className="text-sm text-foreground">{label}</span>
              <Toggle
                checked={!!data.gates[key]}
                onChange={(v) => toggleGate(key, v)}
                disabled={saving}
              />
            </div>
          ))}
        </div>
      </div>

      {/* LLM Providers */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Cpu className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">LLM Providers</h2>
        </div>
        {data.providers.length === 0 ? (
          <p className="text-sm text-muted-foreground">No providers registered</p>
        ) : (
          <div className="space-y-2">
            {data.providers.map((p) => (
              <div key={p.name} className="flex items-center justify-between gap-4">
                <div>
                  <span className="text-sm text-foreground font-medium capitalize">{p.name}</span>
                  {p.available && p.models.length > 0 && (
                    <span className="text-xs text-muted-foreground ml-2">
                      ({p.models.length} model{p.models.length !== 1 ? 's' : ''})
                    </span>
                  )}
                </div>
                <span
                  className={cn(
                    'text-xs px-2 py-0.5 rounded-full',
                    p.available
                      ? 'bg-green-400/10 text-green-400'
                      : 'bg-surface-700 text-muted-foreground',
                  )}
                >
                  {p.available ? 'Connected' : 'Not configured'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* System Info */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Server className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">System Info</h2>
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="text-muted-foreground">Python</div>
          <div className="text-foreground">{data.system_info.python_version}</div>
          <div className="text-muted-foreground">Database size</div>
          <div className="text-foreground">{formatBytes(data.system_info.db_size_bytes)}</div>
          <div className="text-muted-foreground">KB files</div>
          <div className="text-foreground">{data.system_info.kb_file_count} markdown files</div>
        </div>
      </div>

      {/* Actions */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2 mb-4">
          <Database className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">Maintenance</h2>
        </div>
        <div className="flex gap-3">
          <button
            onClick={handleReload}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
          >
            <RefreshCw className={cn('h-4 w-4', saving && 'animate-spin')} />
            Reload Config
          </button>
          <button
            onClick={handleReindex}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
          >
            <Database className="h-4 w-4" />
            Re-index KB
          </button>
        </div>
      </div>

      {/* Reports */}
      <ReportsSection saving={saving} setSaving={setSaving} setStatus={setStatus} />

      {/* Trust Ladder */}
      <TrustLadderSection />

      {/* Security */}
      <SecuritySection saving={saving} setSaving={setSaving} setStatus={setStatus} />

      {/* LLM Routing */}
      <LLMRoutingSection />

      {/* Memory */}
      <MemorySection />
    </div>
  )
}

interface RoutingRule {
  model: string
  description: string
}

interface RoutingData {
  routing_rules: Record<string, RoutingRule>
  providers: Array<{ name: string; available: boolean; models: string[] }>
}

function LLMRoutingSection() {
  const { data } = useApi<RoutingData>('/llm/routing')
  const { data: usageData } = useApi<{ usage: Record<string, unknown> }>('/llm/usage')

  if (!data) return null

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Route className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">LLM Routing</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">How tasks are automatically routed to the best model</p>
      <div className="space-y-2">
        {Object.entries(data.routing_rules).map(([taskType, rule]) => (
          <div key={taskType} className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
            <div>
              <span className="text-sm font-medium text-foreground capitalize">{taskType}</span>
              <span className="text-xs text-muted-foreground ml-2">{rule.description}</span>
            </div>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-brand-400/10 text-brand-400 shrink-0">
              {rule.model}
            </span>
          </div>
        ))}
      </div>

      {usageData?.usage && Object.keys(usageData.usage).length > 0 && (
        <div className="mt-4 pt-4 border-t border-border">
          <h3 className="text-sm font-semibold text-foreground mb-2">Usage Stats</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(usageData.usage).map(([key, val]) => (
              <div key={key} className="flex justify-between">
                <span className="text-muted-foreground capitalize">{key.replace(/_/g, ' ')}</span>
                <span className="text-foreground">{String(val)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

interface MemoryResult {
  content: string
  category: string
  system_key: string
  created_at: string
}

function MemorySection() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MemoryResult[]>([])
  const [searching, setSearching] = useState(false)

  async function handleSearch() {
    if (!query.trim()) return
    setSearching(true)
    try {
      const data = await api.get<{ results: MemoryResult[] }>(`/memory/search?q=${encodeURIComponent(query)}`)
      setResults(data.results || [])
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Brain className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Memory</h2>
      </div>
      <div className="flex gap-2 mb-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search agent memories..."
            className="w-full rounded-lg border border-border bg-surface-800 pl-9 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={searching || !query.trim()}
          className="px-3 py-2 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40 transition-colors"
        >
          Search
        </button>
      </div>
      {results.length > 0 && (
        <div className="space-y-2">
          {results.map((m, i) => (
            <div key={i} className="rounded-lg border border-border p-3">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs px-1.5 py-0.5 rounded bg-surface-700 text-muted-foreground">{m.category}</span>
                {m.system_key && (
                  <span className="text-xs text-muted-foreground font-mono">{m.system_key}</span>
                )}
              </div>
              <p className="text-sm text-foreground whitespace-pre-wrap">{m.content}</p>
            </div>
          ))}
        </div>
      )}
      {results.length === 0 && query && !searching && (
        <p className="text-xs text-muted-foreground">No memories found. Memories are created as agents interact with users.</p>
      )}
    </div>
  )
}

function ReportsSection({ saving, setSaving, setStatus }: { saving: boolean; setSaving: (v: boolean) => void; setStatus: (v: { message: string; type: 'success' | 'error' } | null) => void }) {
  const [generating, setGenerating] = useState<string | null>(null)

  async function triggerReport(type: 'morning-briefing' | 'weekly-review') {
    setGenerating(type)
    setSaving(true)
    setStatus(null)
    try {
      await api.post(`/reports/${type}`)
      const label = type === 'morning-briefing' ? 'Morning Briefing' : 'Weekly Review'
      setStatus({ message: `${label} generated successfully`, type: 'success' })
    } catch (err) {
      setStatus({ message: err instanceof Error ? err.message : 'Report generation failed', type: 'error' })
    } finally {
      setGenerating(null)
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <FileText className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Reports</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">Generate on-demand reports from your system data</p>
      <div className="flex gap-3">
        <button
          onClick={() => triggerReport('morning-briefing')}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          {generating === 'morning-briefing' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
          Morning Briefing
        </button>
        <button
          onClick={() => triggerReport('weekly-review')}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          {generating === 'weekly-review' ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
          Weekly Review
        </button>
      </div>
    </div>
  )
}

// API returns: {level: number, actions: {action_name: {1: "block", 2: "approve", ...}}}
interface TrustData {
  level: number
  actions: Record<string, Record<string, string>>
}

const TRUST_LEVEL_LABELS: Record<number, string> = {
  1: 'Block',
  2: 'Require Approval',
  3: 'Approve (notify)',
  4: 'Auto (log)',
  5: 'Auto (silent)',
}

const DECISION_COLORS: Record<string, string> = {
  block: 'text-red-400 bg-red-400/10',
  approve: 'text-yellow-400 bg-yellow-400/10',
  auto: 'text-green-400 bg-green-400/10',
}

function TrustLadderSection() {
  const { data, refetch } = useApi<TrustData>('/trust')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  if (!data) return null

  const actions = data.actions || {}
  const currentLevel = data.level || 3

  async function changeLevel(newLevel: number) {
    setSaving(true)
    try {
      await api.put('/trust/level', { level: newLevel })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      refetch()
    } catch {
      // Trust API may not be fully enabled
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Shield className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Trust Ladder</h2>
      </div>

      <div className="flex items-center gap-3 mb-4">
        <span className="text-sm text-muted-foreground">System trust level:</span>
        <select
          value={currentLevel}
          onChange={(e) => changeLevel(Number(e.target.value))}
          disabled={saving}
          className="appearance-none bg-surface-800 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
        >
          {[1, 2, 3, 4, 5].map((l) => (
            <option key={l} value={l}>{l} — {TRUST_LEVEL_LABELS[l]}</option>
          ))}
        </select>
        {saved && <Check className="h-4 w-4 text-green-400" />}
      </div>

      <p className="text-xs text-muted-foreground mb-3">At level {currentLevel}, each action type has these permissions:</p>

      <div className="space-y-2">
        {Object.entries(actions).map(([action, rules]) => {
          const decision = rules[String(currentLevel)] || 'auto'
          return (
            <div key={action} className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
              <span className="text-sm text-foreground capitalize">{action.replace(/_/g, ' ')}</span>
              <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', DECISION_COLORS[decision] || 'text-muted-foreground bg-surface-700')}>
                {decision}
              </span>
            </div>
          )
        })}
      </div>

      {Object.keys(actions).length === 0 && (
        <p className="text-xs text-muted-foreground">No trust rules configured. Using defaults.</p>
      )}
    </div>
  )
}

function SecuritySection({ saving, setSaving, setStatus }: { saving: boolean; setSaving: (v: boolean) => void; setStatus: (v: { message: string; type: 'success' | 'error' } | null) => void }) {
  const [scanning, setScanning] = useState(false)

  async function runScan() {
    setScanning(true)
    setSaving(true)
    setStatus(null)
    try {
      const res = await api.post<{ issues: number; report: string }>('/security/scan')
      setStatus({
        message: res.issues === 0 ? 'Security scan passed — no issues found' : `Scan found ${res.issues} issue(s)`,
        type: res.issues === 0 ? 'success' : 'error',
      })
    } catch (err) {
      setStatus({ message: err instanceof Error ? err.message : 'Security scan failed', type: 'error' })
    } finally {
      setScanning(false)
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <ShieldCheck className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Security</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">Run a security audit of your RealizeOS installation</p>
      <button
        onClick={runScan}
        disabled={saving || scanning}
        className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
      >
        {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
        {scanning ? 'Scanning...' : 'Run Security Scan'}
      </button>
    </div>
  )
}
