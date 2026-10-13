import { useEffect, useState } from 'react'
import { AlertCircle, RefreshCw, CheckCircle2, XCircle, AlertTriangle, X } from 'lucide-react'
import { useApi, useInvalidateApi } from '@/hooks/use-api'
import { useAuth } from '@/hooks/use-auth'
import { useLocale } from '@/components/locale-provider'
import { ApprovalCard, DecisionLogLine, type Approval } from '@/components/approval-card'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { canDecide } from '@/lib/permissions'
import {
  approvalOutcome,
  classifyDecisionError,
  isExpired,
  withSettled,
  type DecisionLogResult,
  type DecisionProblem,
  type ExecutionResult,
} from '@/lib/approval-outcome'
import { approvalText, outcomeMessage, type ApprovalText } from '@/lib/approval-text'
import { TitleBlock } from '@/components/ui/title-block'
import { Tabs } from '@/components/ui/tabs'
import { IconButton } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Stamp } from '@/components/ui/stamp'
import { SkeletonCard } from '@/components/ui/skeleton'

interface ApprovalsResponse {
  approvals: Approval[]
}

/** The decide endpoint's answer: the row as decided, plus what ran. */
export interface DecisionResponse extends Approval {
  execution?: ExecutionResult | null
  skill_output?: string | null
  decision_log?: DecisionLogResult | null
}

export type ApprovalsTab = 'pending' | 'decided' | 'expired'

const PATHS: Record<ApprovalsTab, string> = {
  pending: '/approvals?status=pending',
  decided: '/approvals?status=',
  expired: '/approvals?status=expired',
}

/** Statuses the Decided tab shows (expired items have their own tab). */
const DECIDED = new Set<Approval['status']>(['approved', 'rejected', 'answered'])

/** Placeholder for the note box; credentials must never be typed here. */
function notePlaceholder(actionType: string, text: ApprovalText): string {
  if (actionType === 'agent_credential') return text.notePlaceholderCredential
  if (actionType === 'skill_input' || actionType === 'agent_input')
    return text.notePlaceholderAnswer
  return text.notePlaceholder
}

function omit<T>(map: Record<string, T>, key: string): Record<string, T> {
  const next = { ...map }
  delete next[key]
  return next
}

/** A clock that ticks, so an item whose time runs out while the page is open turns expired. */
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}

export default function ApprovalsPage() {
  const { language } = useLocale()
  const text = approvalText(language)
  const { user } = useAuth()
  const now = useNow(15_000)
  const [tab, setTab] = useState<ApprovalsTab>('pending')
  const { data, loading, error } = useApi<ApprovalsResponse>(PATHS[tab])
  const invalidate = useInvalidateApi()
  const [noteMap, setNoteMap] = useState<Record<string, string>>({})
  const [busyId, setBusyId] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<DecisionResponse | null>(null)
  /** Why a decision didn't apply, per item. */
  const [problems, setProblems] = useState<Record<string, DecisionProblem>>({})
  /** Items a refused decision settled (someone else decided, expired): kept in view until refresh. */
  const [settled, setSettled] = useState<Record<string, Approval>>({})

  function clearDecisionState() {
    setOutcome(null)
    setProblems({})
    setSettled({})
  }

  function changeTab(next: ApprovalsTab) {
    clearDecisionState()
    setTab(next)
  }

  function refresh() {
    clearDecisionState()
    invalidate('/approvals')
  }

  async function decide(approval: Approval, verb: 'approve' | 'reject') {
    const id = approval.id
    setBusyId(id)
    setOutcome(null) // a new attempt never sits under the last decision's banner
    setProblems((p) => omit(p, id))
    let signedOut = false
    try {
      const res = await api.post<DecisionResponse>(`/approvals/${id}/${verb}`, {
        decision_note: noteMap[id] || null,
      })
      setOutcome(res)
      setNoteMap((m) => omit(m, id))
    } catch (err) {
      const problem = classifyDecisionError(err)
      // 401: the sign-in page takes over (notifySessionExpired already fired).
      signedOut = problem.kind === 'session'
      setProblems((p) => ({ ...p, [id]: problem }))
      if (problem.final) {
        setSettled((s) => ({ ...s, [id]: { ...approval, ...problem.approval } as Approval }))
      }
    } finally {
      setBusyId(null)
      // Every attempt refreshes every approvals view: this tab, the others,
      // the sidebar badge and the overview.
      if (!signedOut) invalidate('/approvals')
    }
  }

  const fromServer = data?.approvals ?? []
  const approvals = (
    tab === 'pending'
      ? withSettled(fromServer, settled)
      : tab === 'decided'
        ? fromServer.filter((a) => DECIDED.has(a.status))
        : fromServer
  ).slice(0, 50)

  return (
    <ApprovalsView
      text={text}
      language={language}
      tab={tab}
      onTabChange={changeTab}
      onRefresh={refresh}
      approvals={approvals}
      loading={loading}
      error={error}
      now={now}
      blockedReason={canDecide(user) ? null : text.viewOnly(user?.role ?? '')}
      busyId={busyId}
      problems={problems}
      outcome={outcome}
      onDismissOutcome={() => setOutcome(null)}
      onDismissProblem={(id) => {
        setProblems((p) => omit(p, id))
        setSettled((s) => omit(s, id))
      }}
      onDecide={decide}
      notes={noteMap}
      onNoteChange={(id, value) => setNoteMap((m) => ({ ...m, [id]: value }))}
    />
  )
}

export interface ApprovalsViewProps {
  text: ApprovalText
  language: string
  tab: ApprovalsTab
  onTabChange: (tab: ApprovalsTab) => void
  onRefresh: () => void
  approvals: Approval[]
  loading: boolean
  error: string | null
  /** Clock (ms) for expiry. */
  now: number
  /** Set when the person's role can't decide: no decision controls, and this says why. */
  blockedReason: string | null
  busyId: string | null
  problems: Record<string, DecisionProblem>
  outcome: DecisionResponse | null
  onDismissOutcome: () => void
  onDismissProblem: (id: string) => void
  onDecide: (approval: Approval, verb: 'approve' | 'reject') => void
  notes: Record<string, string>
  onNoteChange: (id: string, value: string) => void
}

/** The approvals page as it renders, from plain props. */
export function ApprovalsView({
  text,
  language,
  tab,
  onTabChange,
  onRefresh,
  approvals,
  loading,
  error,
  now,
  blockedReason,
  busyId,
  problems,
  outcome,
  onDismissOutcome,
  onDismissProblem,
  onDecide,
  notes,
  onNoteChange,
}: ApprovalsViewProps) {
  const heldCount = approvals.filter(
    (a) => a.status === 'pending' && !isExpired(a, now) && !problems[a.id]?.final,
  ).length
  return (
    <div className="mx-auto max-w-[960px]">
      <TitleBlock
        title={text.title}
        description={text.description}
        actions={
          <IconButton label={text.refresh} onClick={onRefresh}>
            <RefreshCw />
          </IconButton>
        }
      />

      <Tabs
        label={text.tabsLabel}
        className="mb-6"
        value={tab}
        onChange={onTabChange}
        items={[
          {
            value: 'pending',
            label: text.tabHeld,
            count: tab === 'pending' && !loading ? heldCount : undefined,
          },
          { value: 'decided', label: text.tabDecided },
          { value: 'expired', label: text.tabExpired },
        ]}
      />

      {outcome && (
        <OutcomeBanner outcome={outcome} now={now} text={text} onClose={onDismissOutcome} />
      )}

      {loading ? (
        <div className="grid gap-4" aria-busy="true" aria-label={text.loading}>
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
          title={
            tab === 'pending'
              ? text.emptyHeld
              : tab === 'expired'
                ? text.emptyExpired
                : text.emptyDecided
          }
          body={tab === 'expired' ? text.emptyExpiredBody : text.emptyBody}
        />
      ) : (
        <div className="grid gap-4 rz-stagger">
          {approvals.map((approval, i) => (
            <ApprovalCard
              key={approval.id}
              style={{ ['--i' as string]: i }}
              approval={approval}
              language={language}
              now={now}
              busy={busyId === approval.id}
              problem={problems[approval.id]}
              onDismissProblem={() => onDismissProblem(approval.id)}
              blockedReason={blockedReason}
              onApprove={blockedReason ? undefined : () => onDecide(approval, 'approve')}
              onReject={blockedReason ? undefined : () => onDecide(approval, 'reject')}
            >
              {!blockedReason && (
                <input
                  type="text"
                  dir="auto"
                  aria-label={text.noteLabel}
                  placeholder={notePlaceholder(approval.action_type, text)}
                  value={notes[approval.id] || ''}
                  onChange={(e) => onNoteChange(approval.id, e.target.value)}
                  className="rz-input rz-input--sm"
                />
              )}
            </ApprovalCard>
          ))}
        </div>
      )}
    </div>
  )
}

/**
 * What happened after a decision: done, failed, or unknown, never just
 * "approved". The stamp strikes here, once, as the decision lands.
 */
export function OutcomeBanner({
  outcome,
  now,
  text,
  onClose,
}: {
  outcome: DecisionResponse
  now: number
  text: ApprovalText
  onClose: () => void
}) {
  const result = approvalOutcome(outcome, now, outcome.execution)
  const failed = result.kind === 'failed'
  const unsure = result.kind === 'unknown' || result.kind === 'not_started'
  const ran = failed || unsure || result.kind === 'succeeded'
  const actionName = outcome.action_name || outcome.action_type
  const label = text.actionTypes[actionName] || actionName
  const message = ran || !outcome.skill_output ? outcomeMessage(result, text) : outcome.skill_output
  const Icon = failed ? XCircle : unsure ? AlertTriangle : CheckCircle2
  return (
    <div
      role="status"
      data-outcome={result.kind}
      className={cn(
        'mb-6 flex items-center gap-4 rounded-[10px] border p-4 rz-enter',
        failed
          ? 'border-red-400/30 bg-red-400/10'
          : unsure
            ? 'border-amber-400/30 bg-amber-400/10'
            : 'border-border bg-card',
      )}
    >
      {(outcome.status === 'approved' || outcome.status === 'rejected') && (
        <Stamp
          decision={outcome.status}
          label={text.status[outcome.status]}
          strike
          className="shrink-0"
        />
      )}
      <div className="grid min-w-0 flex-1 gap-1.5">
        <div
          dir="auto"
          className={cn(
            'flex min-w-0 items-start gap-2 text-sm',
            failed ? 'text-red-400' : unsure ? 'text-amber-400' : 'text-foreground',
          )}
        >
          <Icon
            className={cn('mt-0.5 h-4 w-4 shrink-0', !failed && !unsure && 'text-emerald-400')}
          />
          <span className="min-w-0 whitespace-pre-wrap break-words">
            <strong className="font-semibold">{label}</strong> · {message}
          </span>
        </div>
        {ran && outcome.skill_output && (
          <p dir="auto" className="m-0 whitespace-pre-wrap break-words text-[13px] text-foreground">
            {outcome.skill_output}
          </p>
        )}
        {outcome.decision_log && <DecisionLogLine log={outcome.decision_log} text={text} />}
      </div>
      <IconButton label={text.dismiss} size="sm" onClick={onClose}>
        <X />
      </IconButton>
    </div>
  )
}
