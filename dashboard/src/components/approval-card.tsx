import type { CSSProperties, ReactNode } from 'react'
import { Clock, CheckCircle2, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Stamp } from '@/components/ui/stamp'

export interface Approval {
  id: string
  venture_key: string
  agent_key: string
  action_type: string
  payload?: string
  status: 'pending' | 'approved' | 'rejected' | 'expired'
  created_at: string
  expires_at?: string
  decision_note?: string | null
  // v5.7.0 — approvals that execute
  action_name?: string | null
  params_json?: string | null
  requested_by?: string | null
  executed_at?: string | null
  result_json?: string | null
  error?: string | null
}

const actionTypeLabels: Record<string, string> = {
  send_email: 'Send email',
  publish_content: 'Publish content',
  external_api: 'External API call',
  create_event: 'Create event',
  high_cost_llm: 'High-cost model call',
  skill_input: 'Question from a skill',
  agent_decision: 'Decision requested by an agent',
  agent_input: 'Question from an agent',
  agent_credential: 'Credential requested by an agent',
}

/** Items whose payload carries a question for the operator. */
const QUESTION_TYPES = new Set(['skill_input', 'agent_decision', 'agent_input', 'agent_credential'])

const STATUS: Record<
  Approval['status'],
  { label: string; tone: 'accent' | 'success' | 'danger' | 'neutral' }
> = {
  pending: { label: 'Held', tone: 'accent' },
  approved: { label: 'Approved', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'danger' },
  expired: { label: 'Expired', tone: 'neutral' },
}

function parseJson(text?: string | null): unknown {
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/** "in 5 h", "in 2 days" or "now"; the absolute time stays in the tooltip. */
function relativeExpiry(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now()
  if (Number.isNaN(ms)) return ''
  if (ms <= 0) return 'now'
  const h = ms / 3_600_000
  if (h < 1) return `in ${Math.max(1, Math.round(ms / 60_000))} min`
  if (h < 48) return `in ${Math.round(h)} h`
  return `in ${Math.round(h / 24)} days`
}

/** Render parameter values readably; long or nested values as JSON. */
function ParamList({ params }: { params: Record<string, unknown> }) {
  const entries = Object.entries(params)
  if (entries.length === 0) return null
  return (
    <dl className="m-0 grid grid-cols-[minmax(80px,max-content)_1fr] gap-x-4 gap-y-1.5 rounded-[7px] border border-border bg-background/50 px-3 py-2.5 text-[13px]">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-subtle-foreground">{key}</dt>
          <dd dir="auto" className="m-0 min-w-0 break-words text-foreground">
            {typeof value === 'string' ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

interface ApprovalCardProps {
  approval: Approval
  onApprove?: (id: string) => void
  onReject?: (id: string) => void
  busy?: boolean
  /** Extra controls for a held item, shown above the decision buttons (e.g. a note field). */
  children?: ReactNode
  /** Play the stamp: only for the decision that just landed, never on load. */
  strike?: boolean
  className?: string
  style?: CSSProperties
}

/**
 * One held action or question. Held items carry the caution hatch; decided
 * items carry the stamp. Execution results and errors are always shown.
 */
export function ApprovalCard({
  approval,
  onApprove,
  onReject,
  busy,
  children,
  strike,
  className,
  style,
}: ApprovalCardProps) {
  const actionName = approval.action_name || approval.action_type
  const label = actionTypeLabels[actionName] || actionName
  const isPending = approval.status === 'pending'
  const status = STATUS[approval.status] ?? STATUS.expired
  const decided = approval.status === 'approved' || approval.status === 'rejected'

  const payload = parseJson(approval.payload) as
    | { question?: string; params?: Record<string, unknown> }
    | undefined
  const params =
    (parseJson(approval.params_json) as Record<string, unknown> | undefined) ?? payload?.params
  const result = parseJson(approval.result_json) as { output?: string } | undefined
  const question = QUESTION_TYPES.has(approval.action_type) ? payload?.question : undefined
  const hasBody =
    !!question || !!params || !!approval.executed_at || (!!approval.decision_note && !isPending)

  return (
    <article
      className={cn('rz-panel relative overflow-hidden', isPending && 'rz-held', className)}
      aria-label={`${label}: ${status.label}`}
      style={style}
    >
      <header className="flex items-start gap-3 px-4 pt-3.5 pb-3 ps-5">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="m-0 text-[15px] font-semibold text-foreground">{label}</h3>
            {approval.action_name && approval.action_name !== label && (
              <code className="text-[11px] text-subtle-foreground">{approval.action_name}</code>
            )}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-subtle-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="rz-avatar rz-avatar--agent rz-avatar--sm" aria-hidden>
                {approval.agent_key.slice(0, 2).toUpperCase()}
              </span>
              Agent: {approval.agent_key}
            </span>
            <span>Venture: {approval.venture_key}</span>
            {approval.requested_by && <span>For: {approval.requested_by}</span>}
            {approval.expires_at && isPending && (
              <span
                className="inline-flex items-center gap-1"
                title={`Expires: ${new Date(approval.expires_at).toLocaleString()}`}
              >
                <Clock className="h-3 w-3" aria-hidden />
                Expires {relativeExpiry(approval.expires_at)}
              </span>
            )}
          </div>
        </div>
        {decided ? (
          <Stamp
            decision={approval.status === 'approved' ? 'approved' : 'rejected'}
            strike={strike}
            className="me-1 mt-1"
          />
        ) : (
          <Badge tone={status.tone} dot={isPending}>
            {status.label}
          </Badge>
        )}
      </header>

      {hasBody && (
        <div className="grid gap-3 px-4 pb-4 ps-5">
          {question && (
            <p dir="auto" className="m-0 text-[15px] leading-relaxed text-foreground">
              {question}
            </p>
          )}

          {params && <ParamList params={params} />}

          {approval.executed_at && (
            <div
              dir="auto"
              className={cn(
                'flex gap-2 rounded-[7px] px-3 py-2 text-[13px]',
                approval.error
                  ? 'bg-red-400/10 text-red-400'
                  : 'bg-emerald-400/10 text-emerald-400',
              )}
            >
              {approval.error ? (
                <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              ) : (
                <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              )}
              <span className="min-w-0 whitespace-pre-wrap break-words">
                {approval.error ? `Failed: ${approval.error}` : result?.output || 'Done'}
              </span>
            </div>
          )}

          {approval.decision_note && !isPending && (
            <p
              dir="auto"
              className="m-0 border-s-2 border-border-strong ps-3 text-[13px] text-muted-foreground"
            >
              “{approval.decision_note}”
            </p>
          )}
        </div>
      )}

      {isPending && (onApprove || onReject || children) && (
        <footer className="rz-panel__foot grid gap-2.5 ps-5">
          {children}
          {(onApprove || onReject) && (
            <div className="flex flex-wrap justify-end gap-2">
              {onReject && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => onReject(approval.id)}
                >
                  {question ? 'No' : 'Reject'}
                </Button>
              )}
              {onApprove && (
                <Button
                  size="sm"
                  variant="approve"
                  busy={busy}
                  onClick={() => onApprove(approval.id)}
                >
                  {question
                    ? 'Yes / send note'
                    : approval.action_name
                      ? 'Approve & run'
                      : 'Approve'}
                </Button>
              )}
            </div>
          )}
        </footer>
      )}
    </article>
  )
}
