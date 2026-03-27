import { useState } from 'react'
import { Route, Search, Loader2, FileText, Shield, Check } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface RoutingRule {
  model: string
  description: string
}

interface RoutingData {
  routing_rules: Record<string, RoutingRule>
  providers: Array<{ name: string; available: boolean; models: string[] }>
}

export function LLMRoutingSection() {
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
        {Object.entries(data.routing_rules || {}).map(([taskType, rule]) => (
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

export function MemorySection() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<MemoryResult[]>([])
  const [searching, setSearching] = useState(false)

  async function handleSearch() {
    if (!query.trim()) return
    setSearching(true)
    try {
      const res = await api.get<{ results: MemoryResult[] }>(`/memory/search?q=${encodeURIComponent(query)}`)
      setResults(res.results || [])
    } catch {
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Search className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Memory Search</h2>
      </div>
      <div className="flex gap-2 mb-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          placeholder="Search agent memories..."
          className="flex-1 bg-surface-800 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder-muted-foreground outline-none focus:border-brand-400"
        />
        <button
          onClick={handleSearch}
          disabled={searching || !query.trim()}
          className="px-4 py-2 text-sm rounded-lg bg-brand-400 text-black font-medium hover:bg-brand-300 disabled:opacity-50 transition-colors"
        >
          {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Search'}
        </button>
      </div>
      {results.length > 0 && (
        <div className="space-y-2 max-h-48 overflow-y-auto">
          {results.map((r, i) => (
            <div key={i} className="rounded-lg bg-surface-800 p-3 text-xs">
              <div className="flex items-center gap-2 mb-1">
                <span className="px-1.5 py-0.5 rounded bg-brand-400/10 text-brand-400">{r.category}</span>
                <span className="text-muted-foreground">{r.system_key}</span>
              </div>
              <p className="text-foreground">{r.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function ReportsSection({ saving, setSaving, setStatus }: { saving: boolean; setSaving: (v: boolean) => void; setStatus: (v: { message: string; type: 'success' | 'error' } | null) => void }) {
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
  approve: 'text-amber-400 bg-amber-400/10',
  auto: 'text-green-400 bg-green-400/10',
}

export function TrustLadderSection() {
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
