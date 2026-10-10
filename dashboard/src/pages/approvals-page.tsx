import { useState } from 'react'
import { ShieldCheck, AlertCircle, RefreshCw, CheckCircle2, XCircle } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { ApprovalCard, type Approval } from '@/components/approval-card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface ApprovalsResponse {
  approvals: Approval[]
}

interface DecisionResponse extends Approval {
  execution?: { executed: boolean; success: boolean; output: string; error: string | null } | null
  skill_output?: string | null
}

type Tab = 'pending' | 'history'

export default function ApprovalsPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const { data, loading, error, refetch } = useApi<ApprovalsResponse>(
    tab === 'pending' ? '/approvals?status=pending' : '/approvals?status=',
  )
  const [noteMap, setNoteMap] = useState<Record<string, string>>({})
  const [busyId, setBusyId] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<DecisionResponse | null>(null)

  async function decide(id: string, verb: 'approve' | 'reject') {
    setBusyId(id)
    try {
      const res = await api.post<DecisionResponse>(`/approvals/${id}/${verb}`, {
        decision_note: noteMap[id] || null,
      })
      setOutcome(res)
    } finally {
      setBusyId(null)
      refetch()
    }
  }

  const approvals = (data?.approvals ?? [])
    .filter((a) => tab === 'pending' || a.status !== 'pending')
    .slice(0, 50)

  return (
    <div className="space-y-6 rz-animate-fade-up">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Approvals</h1>
          {tab === 'pending' && approvals.length > 0 && (
            <span className="rz-badge rz-badge--accent">{approvals.length} pending</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {(['pending', 'history'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                'rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition-colors',
                tab === t
                  ? 'bg-brand-400/15 text-brand-400'
                  : 'text-muted-foreground hover:bg-surface-700',
              )}
            >
              {t}
            </button>
          ))}
          <button
            onClick={refetch}
            aria-label="Refresh"
            className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-surface-700 hover:text-foreground"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {outcome && <OutcomeBanner outcome={outcome} onClose={() => setOutcome(null)} />}

      {loading ? (
        <div className="flex h-64 items-center justify-center text-muted-foreground">
          Loading approvals...
        </div>
      ) : error ? (
        <div className="flex h-64 flex-col items-center justify-center">
          <AlertCircle className="mx-auto mb-2 h-8 w-8 text-red-400" />
          <p className="text-sm text-red-400">{error}</p>
        </div>
      ) : approvals.length === 0 ? (
        <div className="py-16 text-center">
          <ShieldCheck className="mx-auto mb-3 h-12 w-12 text-muted-foreground/30 rz-animate-float" />
          <p className="text-muted-foreground">
            {tab === 'pending' ? 'No pending approvals' : 'No decisions yet'}
          </p>
          <p className="mt-1 text-xs text-muted-foreground/70">
            Approvals appear here when agents attempt gated actions
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {approvals.map((approval) => (
            <div key={approval.id} className="space-y-2">
              <ApprovalCard
                approval={approval}
                busy={busyId === approval.id}
                onApprove={(id) => decide(id, 'approve')}
                onReject={(id) => decide(id, 'reject')}
              />
              {approval.status === 'pending' && (
                <input
                  type="text"
                  dir="auto"
                  placeholder={
                    approval.action_type === 'skill_input'
                      ? 'Your answer (optional)...'
                      : 'Optional note...'
                  }
                  value={noteMap[approval.id] || ''}
                  onChange={(e) => setNoteMap((m) => ({ ...m, [approval.id]: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function OutcomeBanner({ outcome, onClose }: { outcome: DecisionResponse; onClose: () => void }) {
  const exec = outcome.execution
  const failed = exec?.executed && !exec.success
  const text = exec?.executed
    ? exec.success
      ? `Done — ${outcome.action_name}: ${exec.output || 'completed'}`
      : `${outcome.action_name} failed: ${exec.error}`
    : outcome.skill_output
      ? outcome.skill_output
      : `Request ${outcome.status}.`
  return (
    <div
      dir="auto"
      className={cn(
        'flex items-start gap-2 rounded-xl border p-3 text-sm',
        failed
          ? 'border-red-400/30 bg-red-500/10 text-red-300'
          : 'border-emerald-400/30 bg-emerald-500/10 text-emerald-200',
      )}
    >
      {failed ? (
        <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
      ) : (
        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
      )}
      <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{text}</span>
      <button onClick={onClose} className="text-xs opacity-70 hover:opacity-100">
        Dismiss
      </button>
    </div>
  )
}
