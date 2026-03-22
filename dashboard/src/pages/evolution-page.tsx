import { Sparkles, AlertCircle, RefreshCw, Check, X, ArrowUp, ArrowDown } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Suggestion {
  id: string
  type: string
  title: string
  description: string
  risk_level: string
  status: string
  priority: number
  source: string
  changes: Record<string, unknown>
  created_at: number
}

interface EvolutionResponse {
  suggestions: Suggestion[]
  total: number
  pending: number
}

const riskColors: Record<string, string> = {
  low: 'bg-emerald-400/10 text-emerald-400',
  medium: 'bg-brand-400/10 text-brand-400',
  high: 'bg-red-400/10 text-red-400',
}

const typeLabels: Record<string, string> = {
  new_skill: 'New Skill',
  refine_prompt: 'Prompt Refinement',
  add_tool: 'New Tool',
  config_change: 'Config Change',
  workflow_add: 'New Workflow',
}

export default function EvolutionPage() {
  const { data, loading, error, refetch } = useApi<EvolutionResponse>('/evolution/suggestions')

  async function handleApprove(id: string) {
    await api.post(`/evolution/suggestions/${id}/approve`)
    refetch()
  }

  async function handleDismiss(id: string) {
    await api.post(`/evolution/suggestions/${id}/dismiss`)
    refetch()
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading suggestions...</div>
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    )
  }

  const suggestions = data?.suggestions ?? []
  const pending = suggestions.filter((s) => s.status === 'pending')
  const decided = suggestions.filter((s) => s.status !== 'pending')

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Evolution Inbox</h1>
          {data && data.pending > 0 && (
            <span className="text-xs bg-brand-400/10 text-brand-400 px-2 py-0.5 rounded-full font-medium">
              {data.pending} pending
            </span>
          )}
        </div>
        <button
          onClick={refetch}
          className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {suggestions.length === 0 ? (
        <div className="text-center py-16">
          <Sparkles className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-muted-foreground">No evolution suggestions</p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            Suggestions appear here when the evolution engine detects gaps or improvements
          </p>
        </div>
      ) : (
        <>
          {pending.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-foreground mb-3">Pending Review</h2>
              <div className="space-y-3">
                {pending.map((s) => (
                  <SuggestionCard
                    key={s.id}
                    suggestion={s}
                    onApprove={handleApprove}
                    onDismiss={handleDismiss}
                  />
                ))}
              </div>
            </section>
          )}

          {decided.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold text-muted-foreground mb-3">Previously Reviewed</h2>
              <div className="space-y-2 opacity-60">
                {decided.map((s) => (
                  <SuggestionCard key={s.id} suggestion={s} />
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}

function SuggestionCard({
  suggestion: s,
  onApprove,
  onDismiss,
}: {
  suggestion: Suggestion
  onApprove?: (id: string) => void
  onDismiss?: (id: string) => void
}) {
  const isPending = s.status === 'pending'

  return (
    <div
      className={cn(
        'rounded-xl border bg-card p-4',
        isPending ? 'border-brand-400/20' : 'border-border',
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <h3 className="text-sm font-medium text-foreground">{s.title}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{s.description}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-4">
          <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', riskColors[s.risk_level] || riskColors.low)}>
            {s.risk_level}
          </span>
          <span className="text-xs text-muted-foreground bg-surface-700 px-2 py-0.5 rounded">
            {typeLabels[s.type] || s.type}
          </span>
        </div>
      </div>

      <div className="flex items-center justify-between mt-3">
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            {s.priority >= 0.7 ? <ArrowUp className="h-3 w-3 text-red-400" /> : <ArrowDown className="h-3 w-3" />}
            Priority: {(s.priority * 100).toFixed(0)}%
          </span>
          {s.source && <span>Source: {s.source}</span>}
        </div>

        {isPending && (onApprove || onDismiss) && (
          <div className="flex gap-2">
            {onApprove && (
              <button
                onClick={() => onApprove(s.id)}
                className="flex items-center gap-1 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition-colors"
              >
                <Check className="h-3 w-3" />
                Approve
              </button>
            )}
            {onDismiss && (
              <button
                onClick={() => onDismiss(s.id)}
                className="flex items-center gap-1 rounded-lg bg-surface-700 px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="h-3 w-3" />
                Dismiss
              </button>
            )}
          </div>
        )}

        {!isPending && (
          <span
            className={cn(
              'text-xs px-2 py-0.5 rounded-full',
              s.status === 'applied' && 'bg-emerald-400/10 text-emerald-400',
              s.status === 'rejected' && 'bg-red-400/10 text-red-400',
              s.status === 'approved' && 'bg-brand-400/10 text-brand-400',
            )}
          >
            {s.status}
          </span>
        )}
      </div>
    </div>
  )
}
