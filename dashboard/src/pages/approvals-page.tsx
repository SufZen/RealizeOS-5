import { useState } from 'react'
import { AlertCircle, RefreshCw, CheckCircle2, XCircle, X } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { ApprovalCard, type Approval } from '@/components/approval-card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { TitleBlock } from '@/components/ui/title-block'
import { Tabs } from '@/components/ui/tabs'
import { IconButton } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Stamp } from '@/components/ui/stamp'
import { SkeletonCard } from '@/components/ui/skeleton'

interface ApprovalsResponse {
  approvals: Approval[]
}

interface DecisionResponse extends Approval {
  execution?: { executed: boolean; success: boolean; output: string; error: string | null } | null
  skill_output?: string | null
}

type Tab = 'pending' | 'history'

/** Placeholder for the note box; credentials must never be typed here. */
function notePlaceholder(actionType: string): string {
  if (actionType === 'agent_credential') return 'Add the credential in Setup, not here (not stored)'
  if (actionType === 'skill_input' || actionType === 'agent_input')
    return 'Your answer (optional)...'
  return 'Optional note...'
}

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
    <div className="mx-auto max-w-[960px]">
      <TitleBlock
        title="Approvals"
        description="Payments, messages and questions your agents prepared. Nothing runs until someone here decides."
        actions={
          <IconButton label="Refresh" onClick={refetch}>
            <RefreshCw />
          </IconButton>
        }
      />

      <Tabs
        label="Approvals"
        className="mb-6"
        value={tab}
        onChange={setTab}
        items={[
          {
            value: 'pending',
            label: 'Held for you',
            count: tab === 'pending' && !loading ? approvals.length : undefined,
          },
          { value: 'history', label: 'Decided' },
        ]}
      />

      {outcome && <OutcomeBanner outcome={outcome} onClose={() => setOutcome(null)} />}

      {loading ? (
        <div className="grid gap-4" aria-busy="true" aria-label="Loading approvals">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : error ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-[10px] border border-red-400/30 bg-red-400/10 p-4 text-sm text-red-400"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : approvals.length === 0 ? (
        <EmptyState
          art="approvals"
          title={tab === 'pending' ? 'Nothing is waiting for you' : 'No decisions yet'}
          body="Approvals appear here when agents attempt gated actions: payments, messages to clients, anything that touches money, contracts or people."
        />
      ) : (
        <div className="grid gap-4 rz-stagger">
          {approvals.map((approval, i) => (
            <ApprovalCard
              key={approval.id}
              style={{ ['--i' as string]: i }}
              approval={approval}
              busy={busyId === approval.id}
              onApprove={(id) => decide(id, 'approve')}
              onReject={(id) => decide(id, 'reject')}
            >
              <input
                type="text"
                dir="auto"
                aria-label="Note for this decision"
                placeholder={notePlaceholder(approval.action_type)}
                value={noteMap[approval.id] || ''}
                onChange={(e) => setNoteMap((m) => ({ ...m, [approval.id]: e.target.value }))}
                className="rz-input rz-input--sm"
              />
            </ApprovalCard>
          ))}
        </div>
      )}
    </div>
  )
}

/** What happened after a decision. The stamp strikes here, once, as the decision lands. */
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
  const decision = outcome.status === 'rejected' ? 'rejected' : 'approved'
  return (
    <div
      role="status"
      className={cn(
        'mb-6 flex items-center gap-4 rounded-[10px] border p-4 rz-enter',
        failed ? 'border-red-400/30 bg-red-400/10' : 'border-border bg-card',
      )}
    >
      {(outcome.status === 'approved' || outcome.status === 'rejected') && (
        <Stamp decision={decision} strike className="shrink-0" />
      )}
      <div
        dir="auto"
        className={cn(
          'flex min-w-0 flex-1 items-start gap-2 text-sm',
          failed ? 'text-red-400' : 'text-foreground',
        )}
      >
        {failed ? (
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
        ) : (
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
        )}
        <span className="min-w-0 whitespace-pre-wrap break-words">{text}</span>
      </div>
      <IconButton label="Dismiss" size="sm" onClick={onClose}>
        <X />
      </IconButton>
    </div>
  )
}
