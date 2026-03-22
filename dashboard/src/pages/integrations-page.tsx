import { useState, useCallback, useMemo } from 'react'
import {
  Puzzle,
  Plus,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Loader2,
  Settings2,
  ExternalLink,
  Wifi,
  WifiOff,
  Search,
  RefreshCw,
  Power,
  Trash2,
  Shield,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type IntegrationStatus = 'connected' | 'disconnected' | 'error' | 'pending'

interface Integration {
  id: string
  name: string
  provider: string
  category: string
  status: IntegrationStatus
  description: string
  config_url?: string
  last_sync?: string
  events_received?: number
  error_message?: string
}

interface AvailableIntegration {
  provider: string
  name: string
  description: string
  category: string
  setup_url?: string
  requires_api_key: boolean
}

interface IntegrationsData {
  integrations: Integration[]
  available: AvailableIntegration[]
  categories: string[]
}

/* ------------------------------------------------------------------ */
/* Status styling                                                      */
/* ------------------------------------------------------------------ */

const STATUS_META: Record<IntegrationStatus, { color: string; bg: string; icon: typeof Wifi }> = {
  connected:    { color: 'text-green-400',  bg: 'bg-green-400/10 border-green-400/20', icon: CheckCircle2 },
  disconnected: { color: 'text-surface-500', bg: 'bg-surface-700 border-surface-600',  icon: WifiOff },
  error:        { color: 'text-red-400',    bg: 'bg-red-400/10 border-red-400/20',     icon: XCircle },
  pending:      { color: 'text-amber-400',  bg: 'bg-amber-400/10 border-amber-400/20', icon: Loader2 },
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

export default function IntegrationsPage() {
  const { data, loading, error, refetch } = useApi<IntegrationsData>('/integrations')
  const [filter, setFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [showAddModal, setShowAddModal] = useState(false)
  const [actionInProgress, setActionInProgress] = useState<string | null>(null)

  /* ---- Actions ---- */

  const handleToggle = useCallback(async (id: string, currentStatus: IntegrationStatus) => {
    setActionInProgress(id)
    try {
      const action = currentStatus === 'connected' ? 'disconnect' : 'connect'
      await api.post(`/integrations/${id}/${action}`)
      refetch()
    } catch {
      // Error handled by refetch
    } finally {
      setActionInProgress(null)
    }
  }, [refetch])

  const handleRemove = useCallback(async (id: string) => {
    setActionInProgress(id)
    try {
      await api.delete(`/integrations/${id}`)
      refetch()
    } catch {
      // Error handled by refetch
    } finally {
      setActionInProgress(null)
    }
  }, [refetch])

  const handleTestConnection = useCallback(async (id: string) => {
    setActionInProgress(id)
    try {
      await api.post(`/integrations/${id}/test`)
      refetch()
    } catch {
      // Error handled by refetch
    } finally {
      setActionInProgress(null)
    }
  }, [refetch])

  /* ---- Filtering ---- */

  const filteredIntegrations = useMemo(() => {
    if (!data?.integrations) return []
    let result = data.integrations
    if (filter) {
      result = result.filter((i) => i.category === filter)
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      result = result.filter(
        (i) => i.name.toLowerCase().includes(q) || i.provider.toLowerCase().includes(q),
      )
    }
    return result
  }, [data, filter, searchQuery])

  /* ---- Stats ---- */

  const stats = useMemo(() => {
    if (!data?.integrations) return { total: 0, connected: 0, errors: 0 }
    return {
      total: data.integrations.length,
      connected: data.integrations.filter((i) => i.status === 'connected').length,
      errors: data.integrations.filter((i) => i.status === 'error').length,
    }
  }, [data])

  /* ---- Render ---- */

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading integrations...</div>
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load integrations
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Puzzle className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Integrations</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            title="Refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 font-medium transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Total</span>
            <Puzzle className="h-4 w-4 text-muted-foreground" />
          </div>
          <div className="text-2xl font-bold text-foreground">{stats.total}</div>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Connected</span>
            <Wifi className="h-4 w-4 text-green-400" />
          </div>
          <div className="text-2xl font-bold text-green-400">{stats.connected}</div>
        </div>
        <div className="rounded-xl border border-border bg-card p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-muted-foreground">Errors</span>
            <AlertCircle className="h-4 w-4 text-red-400" />
          </div>
          <div className="text-2xl font-bold text-red-400">{stats.errors}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search integrations..."
            className="pl-8 pr-3 py-1.5 rounded-lg border border-border bg-surface-800 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400 w-60"
          />
        </div>
        <div className="flex gap-1.5">
          <button
            onClick={() => setFilter('')}
            className={cn(
              'px-3 py-1.5 text-xs rounded-lg border transition-colors',
              !filter ? 'border-brand-400 text-brand-400 bg-brand-400/10' : 'border-border text-muted-foreground hover:text-foreground',
            )}
          >
            All
          </button>
          {data.categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={cn(
                'px-3 py-1.5 text-xs rounded-lg border transition-colors capitalize',
                filter === cat ? 'border-brand-400 text-brand-400 bg-brand-400/10' : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Integration cards */}
      {filteredIntegrations.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-40 text-muted-foreground gap-2">
          <Puzzle className="h-8 w-8 opacity-30" />
          <p className="text-sm">No integrations found</p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {filteredIntegrations.map((integration) => (
            <IntegrationCard
              key={integration.id}
              integration={integration}
              isLoading={actionInProgress === integration.id}
              onToggle={() => handleToggle(integration.id, integration.status)}
              onRemove={() => handleRemove(integration.id)}
              onTest={() => handleTestConnection(integration.id)}
            />
          ))}
        </div>
      )}

      {/* Add integration modal */}
      {showAddModal && (
        <AddIntegrationModal
          available={data.available}
          onClose={() => setShowAddModal(false)}
          onAdded={() => { setShowAddModal(false); refetch() }}
        />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Integration Card                                                    */
/* ------------------------------------------------------------------ */

interface IntegrationCardProps {
  integration: Integration
  isLoading: boolean
  onToggle: () => void
  onRemove: () => void
  onTest: () => void
}

function IntegrationCard({ integration, isLoading, onToggle, onRemove, onTest }: IntegrationCardProps) {
  const statusMeta = STATUS_META[integration.status]
  const StatusIcon = statusMeta.icon

  return (
    <div className={cn(
      'rounded-xl border bg-card p-5 transition-all',
      integration.status === 'error' ? 'border-red-400/30' : 'border-border',
    )}>
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-foreground">{integration.name}</h3>
          <span className="text-xs text-muted-foreground capitalize">{integration.provider} · {integration.category}</span>
        </div>
        <span className={cn(
          'flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full border',
          statusMeta.bg, statusMeta.color,
        )}>
          <StatusIcon className={cn('h-3 w-3', integration.status === 'pending' && 'animate-spin')} />
          {integration.status}
        </span>
      </div>

      {/* Description */}
      <p className="text-xs text-muted-foreground mb-3">{integration.description}</p>

      {/* Error message */}
      {integration.status === 'error' && integration.error_message && (
        <div className="flex items-start gap-2 text-xs text-red-400 bg-red-400/5 border border-red-400/10 rounded-lg px-3 py-2 mb-3">
          <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          <span>{integration.error_message}</span>
        </div>
      )}

      {/* Metadata */}
      <div className="flex flex-wrap items-center gap-3 mb-3 text-[10px] text-muted-foreground">
        {integration.last_sync && (
          <span>Last sync: {new Date(integration.last_sync).toLocaleString()}</span>
        )}
        {(integration.events_received ?? 0) > 0 && (
          <span>{integration.events_received} events</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-3 border-t border-border/50">
        <button
          onClick={onToggle}
          disabled={isLoading}
          className={cn(
            'flex items-center gap-1 px-2.5 py-1 text-[10px] rounded-lg border transition-colors',
            integration.status === 'connected'
              ? 'border-red-400/30 text-red-400 hover:bg-red-400/10'
              : 'border-green-400/30 text-green-400 hover:bg-green-400/10',
            isLoading && 'opacity-50',
          )}
        >
          {isLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Power className="h-3 w-3" />}
          {integration.status === 'connected' ? 'Disconnect' : 'Connect'}
        </button>
        <button
          onClick={onTest}
          disabled={isLoading || integration.status !== 'connected'}
          className="flex items-center gap-1 px-2.5 py-1 text-[10px] rounded-lg border border-border text-muted-foreground hover:text-foreground disabled:opacity-40 transition-colors"
        >
          <Shield className="h-3 w-3" /> Test
        </button>
        {integration.config_url && (
          <a
            href={integration.config_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-2.5 py-1 text-[10px] rounded-lg border border-border text-muted-foreground hover:text-foreground transition-colors"
          >
            <Settings2 className="h-3 w-3" /> Configure
          </a>
        )}
        <button
          onClick={onRemove}
          disabled={isLoading}
          className="flex items-center gap-1 px-2.5 py-1 text-[10px] rounded-lg border border-border text-muted-foreground hover:text-red-400 ml-auto disabled:opacity-40 transition-colors"
        >
          <Trash2 className="h-3 w-3" /> Remove
        </button>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Add Integration Modal                                               */
/* ------------------------------------------------------------------ */

interface AddIntegrationModalProps {
  available: AvailableIntegration[]
  onClose: () => void
  onAdded: () => void
}

function AddIntegrationModal({ available, onClose, onAdded }: AddIntegrationModalProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [adding, setAdding] = useState<string | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [selectedProvider, setSelectedProvider] = useState<AvailableIntegration | null>(null)

  const filtered = useMemo(() => {
    if (!searchQuery) return available
    const q = searchQuery.toLowerCase()
    return available.filter(
      (a) => a.name.toLowerCase().includes(q) || a.provider.toLowerCase().includes(q),
    )
  }, [available, searchQuery])

  const handleAdd = useCallback(async (integration: AvailableIntegration) => {
    if (integration.requires_api_key) {
      setSelectedProvider(integration)
      return
    }
    setAdding(integration.provider)
    try {
      await api.post('/integrations', { provider: integration.provider })
      onAdded()
    } catch {
      setAdding(null)
    }
  }, [onAdded])

  const handleAddWithKey = useCallback(async () => {
    if (!selectedProvider || !apiKey) return
    setAdding(selectedProvider.provider)
    try {
      await api.post('/integrations', {
        provider: selectedProvider.provider,
        api_key: apiKey,
      })
      onAdded()
    } catch {
      setAdding(null)
    }
  }, [selectedProvider, apiKey, onAdded])

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-surface-900 border border-border rounded-2xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-5 border-b border-border">
            <h2 className="text-lg font-semibold text-foreground">Add Integration</h2>
            <button
              onClick={onClose}
              className="rounded-lg p-1 text-muted-foreground hover:text-foreground transition-colors"
            >
              <XCircle className="h-5 w-5" />
            </button>
          </div>

          {/* Search */}
          <div className="p-4 border-b border-border">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search available integrations..."
                className="w-full pl-10 pr-3 py-2 rounded-lg border border-border bg-surface-800 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
                autoFocus
              />
            </div>
          </div>

          {/* API key input for selected provider */}
          {selectedProvider && (
            <div className="p-4 border-b border-border bg-brand-400/5">
              <div className="flex items-center gap-2 mb-2">
                <Shield className="h-4 w-4 text-brand-400" />
                <span className="text-sm font-medium text-foreground">
                  API Key for {selectedProvider.name}
                </span>
              </div>
              <div className="flex gap-2">
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Enter API key..."
                  className="flex-1 rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400 font-mono"
                />
                <button
                  onClick={handleAddWithKey}
                  disabled={!apiKey || adding === selectedProvider.provider}
                  className="px-3 py-1.5 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 font-medium disabled:opacity-40 transition-colors"
                >
                  {adding === selectedProvider.provider
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : 'Add'}
                </button>
              </div>
              <button
                onClick={() => { setSelectedProvider(null); setApiKey('') }}
                className="text-xs text-muted-foreground hover:text-foreground mt-2 transition-colors"
              >
                ← Back to list
              </button>
            </div>
          )}

          {/* List */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {filtered.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">No integrations found</p>
            ) : (
              filtered.map((avail) => (
                <div
                  key={avail.provider}
                  className="flex items-center gap-3 rounded-lg border border-border p-3 hover:bg-surface-800/50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-foreground">{avail.name}</span>
                      <span className="text-[10px] text-muted-foreground capitalize px-1.5 py-0.5 rounded bg-surface-700">
                        {avail.category}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{avail.description}</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {avail.setup_url && (
                      <a
                        href={avail.setup_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="p-1.5 rounded text-muted-foreground hover:text-foreground transition-colors"
                        title="Setup docs"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                    <button
                      onClick={() => handleAdd(avail)}
                      disabled={adding === avail.provider}
                      className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 font-medium disabled:opacity-40 transition-colors"
                    >
                      {adding === avail.provider
                        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        : <Plus className="h-3.5 w-3.5" />}
                      Add
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </>
  )
}
