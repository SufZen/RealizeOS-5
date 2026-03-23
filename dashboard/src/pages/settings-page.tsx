import { useState, useEffect } from 'react'
import { Settings, Shield, Cpu, Server, RefreshCw, Database, AlertCircle, Check, Brain, Search, Route, FileText, ShieldCheck, Loader2, HelpCircle, RotateCcw, Cloud, TestTube2, Download, Code, Terminal, GitBranch, AlertTriangle, Activity } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useTour } from '@/components/tour-provider'

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
                    p.available && p.models.length > 0
                      ? 'bg-green-400/10 text-green-400'
                      : p.available
                      ? 'bg-amber-400/10 text-amber-400'
                      : 'bg-surface-700 text-muted-foreground',
                  )}
                >
                  {p.available && p.models.length > 0 ? 'Connected' : p.available ? 'Available' : 'Not configured'}
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
          <div className="text-foreground">
            {data.system_info.db_size_bytes === 0
              ? <span className="text-muted-foreground italic">Empty — will initialize on first chat</span>
              : formatBytes(data.system_info.db_size_bytes)}
          </div>
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

      {/* Storage & Backup */}
      <StorageSection />

      {/* Help & Support */}
      <HelpSection />

      {/* Advanced Developer Settings */}
      <DevModeSection />
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
  const [scanResult, setScanResult] = useState<{
    passed: number; warnings: number; critical: number; total: number;
    checks: Array<{ name: string; status: string; detail: string }>
  } | null>(null)
  const [auditEvents, setAuditEvents] = useState<Array<{
    event_type: string; user: string; detail: string; timestamp: string
  }>>([])
  const [showAudit, setShowAudit] = useState(false)

  // Load security status on mount
  useEffect(() => {
    api.get<{ scan: typeof scanResult }>('/security/status')
      .then(res => { if (res.scan) setScanResult(res.scan) })
      .catch(() => {})
    api.get<{ events: typeof auditEvents }>('/security/events?limit=20')
      .then(res => setAuditEvents(res.events || []))
      .catch(() => {})
  }, [])

  async function runScan() {
    setScanning(true)
    setSaving(true)
    setStatus(null)
    try {
      const res = await api.post<{ issues: number; report: string; scan: typeof scanResult }>('/security/scan')
      if (res.scan) setScanResult(res.scan)
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

  const statusColor = (s: string) => {
    if (s === 'pass') return 'text-emerald-400'
    if (s === 'critical') return 'text-red-400'
    return 'text-amber-400'
  }
  const statusIcon = (s: string) => {
    if (s === 'pass') return '✓'
    if (s === 'critical') return '✕'
    return '⚠'
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">Security Posture</h2>
        </div>
        <button
          onClick={runScan}
          disabled={saving || scanning}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
          {scanning ? 'Scanning...' : 'Run Scan'}
        </button>
      </div>

      {/* Posture summary cards */}
      {scanResult && (
        <>
          <div className="grid grid-cols-4 gap-3 mb-4">
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Total Checks</p>
              <p className="text-xl font-bold text-foreground">{scanResult.total}</p>
            </div>
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Passed</p>
              <p className="text-xl font-bold text-emerald-400">{scanResult.passed}</p>
            </div>
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Warnings</p>
              <p className="text-xl font-bold text-amber-400">{scanResult.warnings}</p>
            </div>
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Critical</p>
              <p className="text-xl font-bold text-red-400">{scanResult.critical}</p>
            </div>
          </div>

          {/* Check details grid */}
          <div className="rounded-lg border border-border overflow-hidden mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-800">
                  <th className="text-left px-3 py-2 text-xs text-muted-foreground font-medium">Check</th>
                  <th className="text-left px-3 py-2 text-xs text-muted-foreground font-medium w-16">Status</th>
                  <th className="text-left px-3 py-2 text-xs text-muted-foreground font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {scanResult.checks.map((c, i) => (
                  <tr key={i} className="border-b border-border/50 last:border-0">
                    <td className="px-3 py-2 text-foreground">{c.name}</td>
                    <td className={cn('px-3 py-2 font-mono font-bold', statusColor(c.status))}>
                      {statusIcon(c.status)}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground text-xs">{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Audit log toggle */}
      <div className="flex items-center justify-between pt-2 border-t border-border">
        <button
          onClick={() => setShowAudit(!showAudit)}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <Activity className="h-4 w-4" />
          {showAudit ? 'Hide' : 'Show'} Audit Log ({auditEvents.length} events)
        </button>
      </div>

      {showAudit && auditEvents.length > 0 && (
        <div className="mt-3 rounded-lg border border-border overflow-hidden max-h-64 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-surface-800 sticky top-0">
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-32">Time</th>
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-24">Type</th>
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-20">User</th>
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium">Detail</th>
              </tr>
            </thead>
            <tbody>
              {auditEvents.map((e, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-1.5 text-muted-foreground font-mono">{e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '—'}</td>
                  <td className="px-3 py-1.5">
                    <span className={cn(
                      'px-1.5 py-0.5 rounded text-[10px] font-medium',
                      e.event_type === 'security' ? 'bg-red-400/10 text-red-400' :
                      e.event_type === 'auth' ? 'bg-amber-400/10 text-amber-400' :
                      'bg-blue-400/10 text-blue-400'
                    )}>
                      {e.event_type}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-foreground">{e.user || '—'}</td>
                  <td className="px-3 py-1.5 text-muted-foreground truncate max-w-xs">{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAudit && auditEvents.length === 0 && (
        <p className="mt-3 text-xs text-muted-foreground text-center py-4">No audit events recorded yet</p>
      )}
    </div>
  )
}

const S3_PROVIDERS = [
  { label: 'AWS S3', value: '', hint: 'Leave endpoint empty for standard AWS S3' },
  { label: 'MinIO (Self-Hosted)', value: 'http://localhost:9000', hint: 'Your MinIO server URL' },
  { label: 'DigitalOcean Spaces', value: 'https://{region}.digitaloceanspaces.com', hint: 'e.g. nyc3, sfo3, sgp1' },
  { label: 'Backblaze B2', value: 'https://s3.{region}.backblazeb2.com', hint: 'e.g. us-west-004' },
  { label: 'Cloudflare R2', value: 'https://{account_id}.r2.cloudflarestorage.com', hint: 'Your CF account ID' },
  { label: 'Custom S3-Compatible', value: '', hint: 'Enter your endpoint URL' },
]

function StorageSection() {
  const [provider, setProvider] = useState('local')
  const [bucket, setBucket] = useState('')
  const [region, setRegion] = useState('us-east-1')
  const [accessKey, setAccessKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [endpointUrl, setEndpointUrl] = useState('')
  const [syncEnabled, setSyncEnabled] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [storageStatus, setStorageStatus] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [stats, setStats] = useState<{ ventures: number; total_size_bytes: number } | null>(null)

  useEffect(() => {
    api.get<{ config: Record<string, string | boolean>; stats: { ventures: number; total_size_bytes: number } }>('/storage/config')
      .then(res => {
        const cfg = res.config
        setProvider((cfg.provider as string) || 'local')
        setBucket((cfg.s3_bucket as string) || '')
        setRegion((cfg.s3_region as string) || 'us-east-1')
        setEndpointUrl((cfg.s3_endpoint_url as string) || '')
        setSyncEnabled(!!(cfg.sync_enabled))
        setStats(res.stats)
      })
      .catch(() => {})
  }, [])

  async function handleTestConnection() {
    setTesting(true)
    setStorageStatus(null)
    try {
      const res = await api.post<{ message: string }>('/storage/test', {
        provider, s3_bucket: bucket, s3_region: region,
        s3_access_key: accessKey, s3_secret_key: secretKey,
        s3_endpoint_url: endpointUrl, sync_enabled: syncEnabled,
      })
      setStorageStatus({ message: res.message, type: 'success' })
    } catch (e: unknown) {
      setStorageStatus({ message: (e as Error).message || 'Connection test failed', type: 'error' })
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setStorageStatus(null)
    try {
      await api.put('/storage/config', {
        provider, s3_bucket: bucket, s3_region: region,
        s3_access_key: accessKey, s3_secret_key: secretKey,
        s3_endpoint_url: endpointUrl, sync_enabled: syncEnabled,
      })
      setStorageStatus({ message: 'Storage configuration saved.', type: 'success' })
    } catch {
      setStorageStatus({ message: 'Failed to save config', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      const res = await api.post<{ message: string; path: string }>('/storage/export')
      setStorageStatus({ message: `${res.message} → ${res.path}`, type: 'success' })
    } catch {
      setStorageStatus({ message: 'Export failed', type: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const inputClass = 'w-full bg-surface-800 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder-muted-foreground outline-none focus:border-brand-400'

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Cloud className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Storage & Backup</h2>
      </div>

      {stats && (
        <p className="text-xs text-muted-foreground mb-4">
          {stats.ventures} venture(s) · {(stats.total_size_bytes / 1024 / 1024).toFixed(1)} MB on disk
        </p>
      )}

      {storageStatus && <StatusBanner message={storageStatus.message} type={storageStatus.type} />}

      <div className="space-y-4 mt-4">
        {/* Provider toggle */}
        <div className="flex items-center justify-between">
          <span className="text-sm text-foreground">Storage backend</span>
          <div className="flex gap-2">
            <button
              onClick={() => setProvider('local')}
              className={cn('px-3 py-1 text-xs rounded-lg border transition-colors',
                provider === 'local'
                  ? 'bg-brand-400/10 text-brand-400 border-brand-400/30'
                  : 'border-border text-muted-foreground hover:text-foreground'
              )}
            >Local</button>
            <button
              onClick={() => setProvider('s3')}
              className={cn('px-3 py-1 text-xs rounded-lg border transition-colors',
                provider === 's3'
                  ? 'bg-brand-400/10 text-brand-400 border-brand-400/30'
                  : 'border-border text-muted-foreground hover:text-foreground'
              )}
            >S3 Cloud</button>
          </div>
        </div>

        {/* S3 Config */}
        {provider === 's3' && (
          <div className="space-y-3 pl-2 border-l-2 border-brand-400/20">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Provider Template</label>
              <select
                onChange={(e) => {
                  const p = S3_PROVIDERS.find(p => p.label === e.target.value)
                  if (p) setEndpointUrl(p.value)
                }}
                className={inputClass}
              >
                {S3_PROVIDERS.map(p => (
                  <option key={p.label} value={p.label}>{p.label} — {p.hint}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Bucket</label>
                <input value={bucket} onChange={e => setBucket(e.target.value)} placeholder="my-realizeos-bucket" className={inputClass} />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Region</label>
                <input value={region} onChange={e => setRegion(e.target.value)} placeholder="us-east-1" className={inputClass} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Access Key</label>
                <input value={accessKey} onChange={e => setAccessKey(e.target.value)} type="password" placeholder="AKIA..." className={inputClass} />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Secret Key</label>
                <input value={secretKey} onChange={e => setSecretKey(e.target.value)} type="password" placeholder="••••••••" className={inputClass} />
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Endpoint URL (custom/non-AWS)</label>
              <input value={endpointUrl} onChange={e => setEndpointUrl(e.target.value)} placeholder="https://..." className={inputClass} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-foreground">Auto-sync enabled</span>
              <Toggle checked={syncEnabled} onChange={setSyncEnabled} />
            </div>
          </div>
        )}

        {/* Sync Status Panel */}
        {syncEnabled && (
          <SyncStatusPanel />
        )}

        {/* Actions */}
        <div className="flex gap-3 pt-2">
          {provider === 's3' && (
            <button
              onClick={handleTestConnection}
              disabled={testing || !bucket}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube2 className="h-4 w-4" />}
              Test Connection
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-brand-400 text-black font-medium hover:bg-brand-300 disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            Save Config
          </button>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
          >
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Export All Data
          </button>
        </div>
      </div>
    </div>
  )
}

function SyncStatusPanel() {
  const [syncInfo, setSyncInfo] = useState<{
    sync_enabled: boolean; is_running: boolean;
    last_sync: { completed_at: string; sync_type: string } | null;
    stats: Record<string, number>
  } | null>(null)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    api.get<typeof syncInfo>('/storage/sync/status')
      .then(res => setSyncInfo(res))
      .catch(() => {})
  }, [syncing])

  async function triggerSync() {
    setSyncing(true)
    try {
      await api.post('/storage/sync/trigger')
    } catch {
      // handled by status refresh
    } finally {
      setTimeout(() => setSyncing(false), 3000)
    }
  }

  if (!syncInfo) return null

  return (
    <div className="rounded-lg bg-surface-800 p-4 border border-border/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-foreground flex items-center gap-2">
          <RefreshCw className={cn('h-4 w-4', syncInfo.is_running && 'animate-spin text-brand-400')} />
          Sync Status
        </span>
        <button
          onClick={triggerSync}
          disabled={syncing || syncInfo.is_running}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-700 text-foreground hover:bg-surface-600 disabled:opacity-50 transition-colors"
        >
          {(syncing || syncInfo.is_running)
            ? <><Loader2 className="h-3 w-3 animate-spin" /> Syncing...</>
            : <><RefreshCw className="h-3 w-3" /> Sync Now</>
          }
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <span className="text-muted-foreground">Status</span>
          <p className={cn('font-medium', syncInfo.is_running ? 'text-brand-400' : 'text-emerald-400')}>
            {syncInfo.is_running ? 'Running' : 'Idle'}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Last Sync</span>
          <p className="text-foreground">
            {syncInfo.last_sync?.completed_at
              ? new Date(syncInfo.last_sync.completed_at).toLocaleString()
              : 'Never'}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Operations</span>
          <p className="text-foreground">
            {Object.entries(syncInfo.stats || {}).map(([k, v]) => `${k}: ${v}`).join(', ') || 'None'}
          </p>
        </div>
      </div>
    </div>
  )
}

function HelpSection() {
  const { startTour } = useTour()

  function resetOnboarding() {
    try {
      localStorage.removeItem('realizeos_onboarding_complete')
      window.location.reload()
    } catch {
      // ignore
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <HelpCircle className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Help & Support</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">Re-run the guided tour or onboarding wizard to learn about RealizeOS features</p>
      <div className="flex gap-3">
        <button
          onClick={startTour}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 transition-colors"
        >
          <RotateCcw className="h-4 w-4" />
          Restart Tour
        </button>
        <button
          onClick={resetOnboarding}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 transition-colors"
        >
          <RotateCcw className="h-4 w-4" />
          Reset Onboarding
        </button>
      </div>
    </div>
  )
}

interface DevModeStatus {
  enabled: boolean
  protection_level: string
  available_levels: string[]
  connected_tools: { key: string; name: string; context_file: string; active: boolean }[]
  last_snapshot: { tag: string; timestamp: string; message: string } | null
}

interface HealthCheck {
  name: string
  status: string
  icon: string
  message: string
  details: string
}

function DevModeSection() {
  const [status, setStatus] = useState<DevModeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [showAcknowledgment, setShowAcknowledgment] = useState(false)
  const [ack1, setAck1] = useState(false)
  const [ack2, setAck2] = useState(false)
  const [ack3, setAck3] = useState(false)
  const [selectedLevel, setSelectedLevel] = useState('standard')
  const [healthResults, setHealthResults] = useState<HealthCheck[] | null>(null)
  const [runningCheck, setRunningCheck] = useState(false)
  const [generatingContext, setGeneratingContext] = useState(false)
  const [creatingSnapshot, setCreatingSnapshot] = useState(false)
  const [actionMessage, setActionMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  useEffect(() => {
    api.get<DevModeStatus>('/devmode/status')
      .then(res => {
        setStatus(res)
        setSelectedLevel(res.protection_level)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function toggleDevMode(enable: boolean) {
    if (enable && !showAcknowledgment) {
      setShowAcknowledgment(true)
      return
    }
    try {
      const res = await api.put<{ status: string; message: string }>('/devmode/toggle', {
        enabled: enable,
        protection_level: selectedLevel,
        acknowledged: ack1 && ack2 && ack3,
      })
      if (res.status === 'ok') {
        setStatus(prev => prev ? { ...prev, enabled: enable, protection_level: selectedLevel } : prev)
        setShowAcknowledgment(false)
        setActionMessage({ text: res.message, type: 'success' })
      } else {
        setActionMessage({ text: res.message, type: 'error' })
      }
    } catch {
      setActionMessage({ text: 'Failed to toggle Developer Mode', type: 'error' })
    }
  }

  async function runHealthCheck() {
    setRunningCheck(true)
    try {
      const res = await api.post<{ checks: HealthCheck[] }>('/devmode/check')
      setHealthResults(res.checks)
    } catch {
      setActionMessage({ text: 'Health check failed', type: 'error' })
    } finally {
      setRunningCheck(false)
    }
  }

  async function generateContext() {
    setGeneratingContext(true)
    try {
      const res = await api.post<{ count: number }>('/devmode/setup', { protection_level: selectedLevel })
      setActionMessage({ text: `Generated ${res.count} context file(s)`, type: 'success' })
      // Refresh status
      const updated = await api.get<DevModeStatus>('/devmode/status')
      setStatus(updated)
    } catch {
      setActionMessage({ text: 'Failed to generate context files', type: 'error' })
    } finally {
      setGeneratingContext(false)
    }
  }

  async function createSnapshot() {
    setCreatingSnapshot(true)
    try {
      const res = await api.post<{ tag: string }>('/devmode/snapshot')
      setActionMessage({ text: `Snapshot created: ${res.tag}`, type: 'success' })
    } catch {
      setActionMessage({ text: 'Failed to create snapshot', type: 'error' })
    } finally {
      setCreatingSnapshot(false)
    }
  }

  const levelDescriptions: Record<string, string> = {
    strict: 'All core + config files are read-only to AI tools',
    standard: 'Core engine protected, config editable with auto-backup',
    relaxed: 'Only security/db files protected, everything else open',
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Loading Developer Mode...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-amber-500/30 bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Code className="h-5 w-5 text-amber-400" />
          <h2 className="text-lg font-semibold text-foreground">Advanced Developer Settings</h2>
          <span className="px-2 py-0.5 text-[10px] font-medium bg-amber-500/20 text-amber-400 rounded-full">ADVANCED</span>
        </div>
        <Toggle
          checked={status?.enabled ?? false}
          onChange={(checked) => toggleDevMode(checked)}
        />
      </div>

      <p className="text-xs text-muted-foreground mb-4">
        Enable integration with local AI coding tools (Claude Code, Gemini CLI, Cursor, etc.) for system development and extension authoring.
      </p>

      {/* Acknowledgment Modal */}
      {showAcknowledgment && (
        <div className="mb-4 p-4 rounded-lg border border-amber-500/30 bg-amber-500/5">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <span className="text-sm font-medium text-amber-400">Before enabling Developer Mode</span>
          </div>
          <div className="space-y-2 mb-4">
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={ack1} onChange={e => setAck1(e.target.checked)} className="mt-0.5 accent-amber-400" />
              I understand that AI tools can modify system files and configurations
            </label>
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={ack2} onChange={e => setAck2(e.target.checked)} className="mt-0.5 accent-amber-400" />
              I will review all AI-generated changes before deploying
            </label>
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={ack3} onChange={e => setAck3(e.target.checked)} className="mt-0.5 accent-amber-400" />
              I accept responsibility for modifications made by external AI tools
            </label>
          </div>
          <div className="flex gap-2">
            <button
              disabled={!(ack1 && ack2 && ack3)}
              onClick={() => toggleDevMode(true)}
              className="px-4 py-1.5 text-xs rounded-lg bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40 transition-colors"
            >
              Enable Developer Mode
            </button>
            <button
              onClick={() => { setShowAcknowledgment(false); setAck1(false); setAck2(false); setAck3(false) }}
              className="px-4 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:bg-surface-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Action message */}
      {actionMessage && (
        <div className={cn('mb-4 px-3 py-2 rounded-lg text-xs', actionMessage.type === 'success' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400')}>
          {actionMessage.text}
        </div>
      )}

      {status?.enabled && (
        <div className="space-y-4">
          {/* Protection Level */}
          <div>
            <label className="text-xs font-medium text-foreground mb-1 block">Protection Level</label>
            <select
              value={selectedLevel}
              onChange={e => setSelectedLevel(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground"
            >
              {(status.available_levels || ['strict', 'standard', 'relaxed']).map(level => (
                <option key={level} value={level}>{level.charAt(0).toUpperCase() + level.slice(1)}</option>
              ))}
            </select>
            <p className="text-[10px] text-muted-foreground mt-1">{levelDescriptions[selectedLevel] || ''}</p>
          </div>

          {/* Connected AI Tools */}
          <div>
            <label className="text-xs font-medium text-foreground mb-2 block">Connected AI Tools</label>
            <div className="grid grid-cols-2 gap-2">
              {(status.connected_tools || []).length > 0 ? (
                status.connected_tools.map(tool => (
                  <div key={tool.key} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-800 border border-border">
                    <div className="h-2 w-2 rounded-full bg-green-400" />
                    <span className="text-xs text-foreground">{tool.name}</span>
                    <span className="text-[10px] text-muted-foreground ml-auto">{tool.context_file}</span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted-foreground col-span-2">No context files generated yet. Click "Generate Context Files" below.</p>
              )}
            </div>
          </div>

          {/* Last Snapshot */}
          {status.last_snapshot && (
            <div className="px-3 py-2 rounded-lg bg-surface-800 border border-border">
              <div className="flex items-center gap-2">
                <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs text-foreground">Last snapshot: {status.last_snapshot.tag}</span>
                <span className="text-[10px] text-muted-foreground ml-auto">{status.last_snapshot.timestamp}</span>
              </div>
            </div>
          )}

          {/* Health Check Results */}
          {healthResults && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-foreground mb-1 block">Health Check Results</label>
              {healthResults.map((check, i) => (
                <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded bg-surface-800 text-xs">
                  <span>{check.icon}</span>
                  <span className="text-foreground font-medium">{check.name}</span>
                  <span className="text-muted-foreground">{check.message}</span>
                </div>
              ))}
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
            <button
              onClick={generateContext}
              disabled={generatingContext}
              className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {generatingContext ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Terminal className="h-3.5 w-3.5" />}
              Generate Context Files
            </button>
            <button
              onClick={runHealthCheck}
              disabled={runningCheck}
              className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {runningCheck ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              Run Health Check
            </button>
            <button
              onClick={createSnapshot}
              disabled={creatingSnapshot}
              className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {creatingSnapshot ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitBranch className="h-3.5 w-3.5" />}
              Create Snapshot
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
