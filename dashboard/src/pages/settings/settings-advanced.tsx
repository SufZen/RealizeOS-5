import { useId, useState } from 'react'
import { Route, Search, Loader2, FileText, Shield, Check } from 'lucide-react'
import { useApi, useInvalidateApi } from '@/hooks/use-api'
import { useVenture } from '@/hooks/use-venture'
import { useLocale } from '@/components/locale-provider'
import { VentureTrustPanel } from '@/components/venture-trust'
import { api } from '@/lib/api'
import {
  canonicalProvider,
  deadModels,
  formFromSettings,
  modelSuggestions,
  primaryChoices,
  routingUpdate,
  saveRouting,
  TIERS,
  type RoutingData,
  type RoutingForm,
  type RoutingUpdate,
} from '@/lib/llm-routing'
import { llmSettingsText, type LlmSettingsText } from '@/lib/llm-settings-text'
import type { VentureTrust } from '@/lib/trust-copy'
import { cn } from '@/lib/utils'

/** Field look shared by the routing form's inputs. */
const FIELD =
  'w-full bg-surface-800 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder-muted-foreground outline-none focus:border-brand-400'

/**
 * The routing form: primary provider, a model per tier, the fallback order.
 * It starts from the settings as configured (empty = unset, so the default
 * shows as the placeholder) and sends only what changed.
 */
export function LLMRoutingForm({
  data,
  text,
  onSave,
}: {
  data: RoutingData
  text: LlmSettingsText
  onSave: (update: RoutingUpdate) => Promise<void>
}) {
  const [form, setForm] = useState<RoutingForm>(() => formFromSettings(data.settings))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const listId = useId()
  const update = routingUpdate(form, data.settings)
  const suggestions = modelSuggestions(data.providers ?? [])

  // Providers that can answer, plus the current choice if it can't (so it stays visible).
  const options = (data.providers ?? []).filter(
    (p) => p.available || canonicalProvider(p.name) === form.primary,
  )
  // The saved primary is shown even when the server lists no provider by that name
  // (not registered), so the select never reads "automatic" while a primary is saved.
  const unlisted = primaryChoices(
    options.map((p) => p.name),
    form.primary,
  ).filter((name) => !options.some((p) => canonicalProvider(p.name) === name))

  function edit(next: Partial<RoutingForm>) {
    setForm((f) => ({ ...f, ...next }))
    setSaved(false)
  }

  async function handleSave() {
    if (!update) return
    setSaving(true)
    setError('')
    try {
      await onSave(update)
      setSaved(true)
    } catch (err) {
      setError(text.saveError(err instanceof Error ? err.message.trim() : ''))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        void handleSave()
      }}
    >
      <div>
        <label htmlFor={`${listId}-primary`} className="text-sm font-medium text-foreground">
          {text.primaryLabel}
        </label>
        <select
          id={`${listId}-primary`}
          value={form.primary}
          onChange={(e) => edit({ primary: e.target.value })}
          className={cn(FIELD, 'mt-1')}
        >
          <option value="">{text.primaryAuto}</option>
          {options.map((p) => (
            <option key={p.name} value={canonicalProvider(p.name)}>
              {p.available ? p.name : `${p.name} (${text.notAvailable})`}
            </option>
          ))}
          {unlisted.map((name) => (
            <option key={name} value={name}>
              {`${name} (${text.notAvailable})`}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-muted-foreground">{text.primaryHelp}</p>
      </div>

      <fieldset className="space-y-3 border-0 p-0">
        <legend className="text-sm font-medium text-foreground">{text.tiersTitle}</legend>
        {TIERS.map((tier) => (
          <div key={tier}>
            <label htmlFor={`${listId}-${tier}`} className="text-xs text-foreground">
              {text.tierLabel[tier]}
              <span className="text-muted-foreground"> · {text.tierHelp[tier]}</span>
            </label>
            <input
              id={`${listId}-${tier}`}
              dir="auto"
              list={`${listId}-models`}
              value={form.tiers[tier]}
              onChange={(e) => edit({ tiers: { ...form.tiers, [tier]: e.target.value } })}
              placeholder={data.tiers?.[tier]?.model || text.modelPlaceholder}
              autoComplete="off"
              spellCheck={false}
              className={cn(FIELD, 'mt-1 font-mono')}
            />
          </div>
        ))}
        <datalist id={`${listId}-models`}>
          {suggestions.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </fieldset>

      <div>
        <label htmlFor={`${listId}-fallback`} className="text-sm font-medium text-foreground">
          {text.fallbackLabel}
        </label>
        <input
          id={`${listId}-fallback`}
          dir="auto"
          value={form.fallback}
          onChange={(e) => edit({ fallback: e.target.value })}
          placeholder={text.fallbackPlaceholder}
          autoComplete="off"
          spellCheck={false}
          className={cn(FIELD, 'mt-1 font-mono')}
        />
        <p className="mt-1 text-xs text-muted-foreground">{text.fallbackHelp}</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={saving || !update}
          className="px-4 py-2 text-sm rounded-lg bg-brand-400 text-black font-medium hover:bg-brand-300 disabled:opacity-50 transition-colors"
        >
          {saving ? text.saving : text.save}
        </button>
        {saved && !update && (
          <span role="status" className="flex items-center gap-1 text-xs text-green-400">
            <Check className="h-3.5 w-3.5" aria-hidden />
            {text.saved}
          </span>
        )}
        {!update && !saved && (
          <span className="text-xs text-muted-foreground">{text.nothingToSave}</span>
        )}
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}
    </form>
  )
}

export function LLMRoutingSection() {
  const { data } = useApi<RoutingData>('/llm/routing')
  const { data: usageData } = useApi<{ usage: Record<string, unknown> }>('/llm/usage')
  const invalidate = useInvalidateApi()
  const text = llmSettingsText(useLocale().language)

  if (!data) return null

  async function save(update: RoutingUpdate) {
    await saveRouting(update)
    invalidate('/llm/routing')
  }

  const dead = deadModels(data.providers || [])

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Route className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">{text.title}</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">{text.subtitle}</p>

      <LLMRoutingForm data={data} text={text} onSave={save} />

      <h3 className="mt-6 mb-2 text-sm font-semibold text-foreground">{text.rulesTitle}</h3>
      <div className="space-y-2">
        {Object.entries(data.routing_rules || {}).map(([taskType, rule]) => (
          <div
            key={taskType}
            className="flex items-center justify-between gap-4 rounded-lg border border-border p-3"
          >
            <div>
              <span className="text-sm font-medium text-foreground capitalize">{taskType}</span>
              <span className="text-xs text-muted-foreground ms-2">{rule.description}</span>
            </div>
            <bdi className="inline-block text-xs font-mono px-2 py-0.5 rounded bg-brand-400/10 text-brand-400 shrink-0">
              {rule.model}
            </bdi>
          </div>
        ))}
      </div>

      {dead.length > 0 && (
        <div role="alert" className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 p-3">
          <p className="text-sm font-medium text-red-400">{text.deadTitle}</p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            {dead.map(({ provider, model }) => (
              <li key={`${provider}:${model}`}>{text.deadLine(model, provider)}</li>
            ))}
          </ul>
        </div>
      )}

      {usageData?.usage && Object.keys(usageData.usage).length > 0 && (
        <div className="mt-4 pt-4 border-t border-border">
          <h3 className="text-sm font-semibold text-foreground mb-2">{text.usageTitle}</h3>
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
      const res = await api.get<{ results: MemoryResult[] }>(
        `/memory/search?q=${encodeURIComponent(query)}`,
      )
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
                <span className="px-1.5 py-0.5 rounded bg-brand-400/10 text-brand-400">
                  {r.category}
                </span>
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

export function ReportsSection({
  saving,
  setSaving,
  setStatus,
}: {
  saving: boolean
  setSaving: (v: boolean) => void
  setStatus: (v: { message: string; type: 'success' | 'error' } | null) => void
}) {
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
      setStatus({
        message: err instanceof Error ? err.message : 'Report generation failed',
        type: 'error',
      })
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
      <p className="text-xs text-muted-foreground mb-4">
        Generate on-demand reports from your system data
      </p>
      <div className="flex gap-3">
        <button
          onClick={() => triggerReport('morning-briefing')}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          {generating === 'morning-briefing' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          Morning Briefing
        </button>
        <button
          onClick={() => triggerReport('weekly-review')}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          {generating === 'weekly-review' ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FileText className="h-4 w-4" />
          )}
          Weekly Review
        </button>
      </div>
    </div>
  )
}

interface TrustData {
  level: number
  actions: Record<string, Record<string, string>>
  /** Each venture's effective decisions after its packs (only with `features.packs` on). */
  ventures?: Record<string, VentureTrust>
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
  const { selected } = useVenture()
  const { language } = useLocale()
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  if (!data) return null

  const ventureKeys = Object.keys(data.ventures || {})
  const ventureKey = selected && data.ventures?.[selected] ? selected : ventureKeys[0]
  const ventureTrust = ventureKey ? data.ventures?.[ventureKey] : undefined

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
            <option key={l} value={l}>
              {l} — {TRUST_LEVEL_LABELS[l]}
            </option>
          ))}
        </select>
        {saved && <Check className="h-4 w-4 text-green-400" />}
      </div>

      <p className="text-xs text-muted-foreground mb-3">
        At level {currentLevel}, each action type has these permissions:
      </p>

      <div className="space-y-2">
        {Object.entries(actions).map(([action, rules]) => {
          const decision = rules[String(currentLevel)] || 'auto'
          return (
            <div
              key={action}
              className="flex items-center justify-between gap-4 rounded-lg border border-border p-3"
            >
              <span className="text-sm text-foreground capitalize">
                {action.replace(/_/g, ' ')}
              </span>
              <span
                className={cn(
                  'text-xs px-2 py-0.5 rounded-full font-medium',
                  DECISION_COLORS[decision] || 'text-muted-foreground bg-surface-700',
                )}
              >
                {decision}
              </span>
            </div>
          )
        })}
      </div>

      {Object.keys(actions).length === 0 && (
        <p className="text-xs text-muted-foreground">No trust rules configured. Using defaults.</p>
      )}

      {ventureTrust && (
        <div className="mt-4">
          <VentureTrustPanel key={ventureKey} venture={ventureTrust} language={language} />
        </div>
      )}
    </div>
  )
}
