import { ShieldCheck, Clock, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'

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
  send_email: 'Send Email',
  publish_content: 'Publish Content',
  external_api: 'External API Call',
  create_event: 'Create Event',
  high_cost_llm: 'High-Cost LLM',
  skill_input: 'Question from a skill',
}

function parseJson(text?: string | null): unknown {
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/** Render parameter values readably; long or nested values as JSON. */
function ParamList({ params }: { params: Record<string, unknown> }) {
  const entries = Object.entries(params)
  if (entries.length === 0) return null
  return (
    <dl className="mb-3 space-y-1 rounded-lg bg-surface-800/60 p-2 text-xs">
      {entries.map(([key, value]) => (
        <div key={key} className="flex gap-2">
          <dt className="shrink-0 font-medium text-muted-foreground">{key}</dt>
          <dd dir="auto" className="min-w-0 break-words text-foreground">
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
  className?: string
}

export function ApprovalCard({
  approval,
  onApprove,
  onReject,
  busy,
  className,
}: ApprovalCardProps) {
  const actionName = approval.action_name || approval.action_type
  const label = actionTypeLabels[actionName] || actionName
  const isPending = approval.status === 'pending'

  const payload = parseJson(approval.payload) as
    | { question?: string; params?: Record<string, unknown> }
    | undefined
  const params =
    (parseJson(approval.params_json) as Record<string, unknown> | undefined) ?? payload?.params
  const result = parseJson(approval.result_json) as { output?: string } | undefined
  const question = approval.action_type === 'skill_input' ? payload?.question : undefined

  return (
    <div
      className={cn(
        'rounded-xl border bg-card p-4',
        isPending ? 'border-brand-400/30' : 'border-border opacity-80',
        className,
      )}
    >
      <div className="mb-2 flex items-start justify-between">
        <div className="flex items-center gap-2">
          {isPending ? (
            <AlertTriangle className="h-4 w-4 text-brand-400" />
          ) : (
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="text-sm font-medium text-foreground">{label}</span>
          {approval.action_name && approval.action_name !== label && (
            <code className="text-[11px] text-muted-foreground">{approval.action_name}</code>
          )}
        </div>
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-xs font-medium',
            isPending && 'bg-brand-400/10 text-brand-400',
            approval.status === 'approved' && 'bg-emerald-400/10 text-emerald-400',
            approval.status === 'rejected' && 'bg-red-400/10 text-red-400',
            approval.status === 'expired' && 'bg-muted text-muted-foreground',
          )}
        >
          {approval.status}
        </span>
      </div>

      <div className="mb-3 text-xs text-muted-foreground">
        <span>Agent: {approval.agent_key}</span>
        <span className="mx-1">&middot;</span>
        <span>Venture: {approval.venture_key}</span>
        {approval.requested_by && (
          <>
            <span className="mx-1">&middot;</span>
            <span>For: {approval.requested_by}</span>
          </>
        )}
      </div>

      {question && (
        <p dir="auto" className="mb-3 text-sm text-foreground">
          {question}
        </p>
      )}

      {params && <ParamList params={params} />}

      {approval.executed_at && (
        <div
          dir="auto"
          className={cn(
            'mb-3 flex gap-2 rounded-lg p-2 text-xs',
            approval.error ? 'bg-red-500/10 text-red-300' : 'bg-emerald-500/10 text-emerald-300',
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
        <p dir="auto" className="mb-3 text-xs italic text-muted-foreground">
          “{approval.decision_note}”
        </p>
      )}

      {approval.expires_at && isPending && (
        <div className="mb-3 flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span>Expires: {new Date(approval.expires_at).toLocaleString()}</span>
        </div>
      )}

      {isPending && (onApprove || onReject) && (
        <div className="flex gap-2">
          {onApprove && (
            <button
              disabled={busy}
              onClick={() => onApprove(approval.id)}
              className="flex-1 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 transition-colors hover:bg-emerald-500/20 disabled:opacity-50"
            >
              {question ? 'Yes / send note' : approval.action_name ? 'Approve & run' : 'Approve'}
            </button>
          )}
          {onReject && (
            <button
              disabled={busy}
              onClick={() => onReject(approval.id)}
              className="flex-1 rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/20 disabled:opacity-50"
            >
              {question ? 'No' : 'Reject'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
