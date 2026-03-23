import { useState } from 'react'
import {
  Plug,
  Brain,
  Globe,
  Monitor,
  Mail,
  CreditCard,
  Radio,
  Settings2,
  Check,
  AlertCircle,
  Eye,
  EyeOff,
  Loader2,
  Server,
  Search,
  Wrench,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Connection {
  id: string
  name: string
  category: string
  env_key: string
  type: 'secret' | 'toggle' | 'url' | 'number'
  configured: boolean
  masked_value: string | null
  description: string
  help: string
}

interface ConnectionsData {
  connections: Connection[]
  categories: string[]
}

const CATEGORY_LABELS: Record<string, { label: string; icon: typeof Plug }> = {
  llm: { label: 'LLM Providers', icon: Brain },
  tool: { label: 'Search & Tools', icon: Wrench },
  integration: { label: 'Integrations', icon: Globe },
  channel: { label: 'Channels', icon: Radio },
  system: { label: 'System', icon: Settings2 },
}

const CONN_ICONS: Record<string, typeof Plug> = {
  anthropic: Brain,
  google_ai: Brain,
  openai: Brain,
  ollama: Server,
  brave_search: Search,
  browser: Monitor,
  mcp: Plug,
  google_client_id: Mail,
  google_client_secret: Mail,
  stripe: CreditCard,
  telegram: Radio,
  rate_limit: Settings2,
  cost_limit: Settings2,
}

function ConnectionCard({
  conn,
  onSaved,
}: {
  conn: Connection
  onSaved: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const [showValue, setShowValue] = useState(false)
  const [status, setStatus] = useState<{ msg: string; ok: boolean } | null>(null)

  const Icon = CONN_ICONS[conn.id] || Plug

  async function handleSave() {
    setSaving(true)
    setStatus(null)
    try {
      await api.put('/setup/connection', { id: conn.id, value })
      setStatus({ msg: 'Saved', ok: true })
      setValue('')
      setEditing(false)
      onSaved()
    } catch (err) {
      setStatus({ msg: err instanceof Error ? err.message : 'Failed', ok: false })
    } finally {
      setSaving(false)
    }
  }

  async function handleToggle() {
    const newVal = conn.configured ? 'false' : 'true'
    setSaving(true)
    setStatus(null)
    try {
      await api.put('/setup/connection', { id: conn.id, value: newVal })
      onSaved()
    } catch (err) {
      setStatus({ msg: err instanceof Error ? err.message : 'Failed', ok: false })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className={cn(
      'rounded-xl border p-5 transition-colors',
      conn.configured ? 'border-green-400/30 bg-green-400/5' : 'border-border bg-card',
    )}>
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-3">
          <div className={cn(
            'flex items-center justify-center w-10 h-10 rounded-lg',
            conn.configured ? 'bg-green-400/10' : 'bg-surface-700',
          )}>
            <Icon className={cn('h-5 w-5', conn.configured ? 'text-green-400' : 'text-muted-foreground')} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-foreground">{conn.name}</h3>
            <p className="text-xs text-muted-foreground">{conn.description}</p>
          </div>
        </div>

        {conn.configured ? (
          <span className="flex items-center gap-1 text-xs text-green-400 px-2 py-1 rounded-lg bg-green-400/10 shrink-0">
            <Check className="h-3.5 w-3.5" />
            {conn.type === 'toggle' ? 'Enabled' : 'Connected'}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground px-2 py-1 rounded-lg bg-surface-700 shrink-0">
            Not configured
          </span>
        )}
      </div>

      {/* Masked current value */}
      {conn.masked_value && conn.type !== 'toggle' && !editing && (
        <div className="text-xs text-muted-foreground font-mono mt-2">
          {conn.type === 'secret'
            ? `••••••••${conn.masked_value.split('...')[1] ?? ''}`
            : conn.type === 'number' && conn.id === 'rate_limit'
            ? `${conn.masked_value} requests/min`
            : conn.type === 'number' && conn.id === 'cost_limit'
            ? `$${conn.masked_value}/hour`
            : conn.masked_value}
        </div>
      )}

      {/* Toggle type */}
      {conn.type === 'toggle' && (
        <div className="mt-3">
          <button
            onClick={handleToggle}
            disabled={saving}
            className={cn(
              'relative inline-flex h-6 w-11 items-center rounded-full transition-colors',
              conn.configured ? 'bg-green-400' : 'bg-surface-600',
              saving && 'opacity-50',
            )}
          >
            <span className={cn(
              'inline-block h-4 w-4 rounded-full bg-white transition-transform',
              conn.configured ? 'translate-x-6' : 'translate-x-1',
            )} />
          </button>
        </div>
      )}

      {/* Configure button / form */}
      {conn.type !== 'toggle' && !editing && (
        <button
          onClick={() => setEditing(true)}
          className="mt-3 text-xs text-brand-400 hover:text-brand-400/80 transition-colors"
        >
          {conn.configured ? 'Update' : 'Configure'}
        </button>
      )}

      {conn.type !== 'toggle' && editing && (
        <div className="mt-3 space-y-2">
          <div className="relative">
            <input
              type={showValue || conn.type !== 'secret' ? 'text' : 'password'}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && value.trim() && handleSave()}
              placeholder={conn.help || `Enter ${conn.env_key}`}
              className="w-full rounded-lg border border-border bg-surface-800 px-3 py-2 pr-10 text-sm text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-brand-400"
              autoFocus
            />
            {conn.type === 'secret' && (
              <button
                onClick={() => setShowValue(!showValue)}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleSave}
              disabled={saving || !value.trim()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40 font-medium transition-colors"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              Save
            </button>
            <button
              onClick={() => { setEditing(false); setValue(''); setStatus(null) }}
              className="px-3 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:text-foreground transition-colors"
            >
              Cancel
            </button>
            {conn.configured && (
              <button
                onClick={async () => {
                  setSaving(true)
                  try {
                    await api.put('/setup/connection', { id: conn.id, value: '' })
                    setEditing(false)
                    setValue('')
                    onSaved()
                  } catch { /* ignore */ } finally { setSaving(false) }
                }}
                disabled={saving}
                className="px-3 py-1.5 text-xs rounded-lg border border-red-400/30 text-red-400 hover:bg-red-400/10 transition-colors ml-auto"
              >
                Disconnect
              </button>
            )}
          </div>
        </div>
      )}

      {status && (
        <div className={cn(
          'flex items-center gap-1.5 text-xs mt-2',
          status.ok ? 'text-green-400' : 'text-red-400',
        )}>
          {status.ok ? <Check className="h-3.5 w-3.5" /> : <AlertCircle className="h-3.5 w-3.5" />}
          {status.msg}
        </div>
      )}
    </div>
  )
}

export default function SetupPage() {
  const { data, loading, error, refetch } = useApi<ConnectionsData>('/setup/connections')

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading connections...</div>
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load connections
      </div>
    )
  }

  const connectedCount = data.connections.filter((c) => c.configured).length
  const totalCount = data.connections.length

  // Group by category
  const byCategory = data.categories
    .map((cat) => ({
      category: cat,
      ...CATEGORY_LABELS[cat] || { label: cat, icon: Plug },
      connections: data.connections.filter((c) => c.category === cat),
    }))
    .filter((g) => g.connections.length > 0)

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Plug className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Setup & Connections</h1>
        </div>
        <span className="text-sm text-muted-foreground">
          {connectedCount}/{totalCount} connected
        </span>
      </div>

      <p className="text-sm text-muted-foreground">
        Configure your LLM providers, tools, and integrations. Changes take effect immediately.
      </p>

      {connectedCount === 0 && (
        <div className="rounded-xl border border-brand-400/30 bg-brand-400/5 p-5">
          <h2 className="text-sm font-semibold text-brand-400 mb-1">Get Started</h2>
          <p className="text-xs text-muted-foreground">
            Start by connecting at least one LLM provider (Claude, Gemini, OpenAI, or Ollama).
            This is the only requirement — everything else is optional.
          </p>
        </div>
      )}

      {byCategory.map((group) => {
        const CatIcon = group.icon
        return (
          <div key={group.category}>
            <div className="flex items-center gap-2 mb-3">
              <CatIcon className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold text-foreground uppercase tracking-wide">{group.label}</h2>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {group.connections.map((conn) => (
                <ConnectionCard key={conn.id} conn={conn} onSaved={refetch} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
