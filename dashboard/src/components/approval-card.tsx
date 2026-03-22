import { ShieldCheck, Clock, AlertTriangle } from 'lucide-react'
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
}

const actionTypeLabels: Record<string, string> = {
  send_email: 'Send Email',
  publish_content: 'Publish Content',
  external_api: 'External API Call',
  create_event: 'Create Event',
  high_cost_llm: 'High-Cost LLM',
}

interface ApprovalCardProps {
  approval: Approval
  onApprove?: (id: string) => void
  onReject?: (id: string) => void
  className?: string
}

export function ApprovalCard({ approval, onApprove, onReject, className }: ApprovalCardProps) {
  const label = actionTypeLabels[approval.action_type] || approval.action_type
  const isPending = approval.status === 'pending'

  return (
    <div
      className={cn(
        'rounded-xl border bg-card p-4',
        isPending ? 'border-brand-400/30' : 'border-border opacity-70',
        className,
      )}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          {isPending ? (
            <AlertTriangle className="h-4 w-4 text-brand-400" />
          ) : (
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          )}
          <span className="text-sm font-medium text-foreground">{label}</span>
        </div>
        <span
          className={cn(
            'text-xs px-2 py-0.5 rounded-full font-medium',
            isPending && 'bg-brand-400/10 text-brand-400',
            approval.status === 'approved' && 'bg-emerald-400/10 text-emerald-400',
            approval.status === 'rejected' && 'bg-red-400/10 text-red-400',
            approval.status === 'expired' && 'bg-muted text-muted-foreground',
          )}
        >
          {approval.status}
        </span>
      </div>

      <div className="text-xs text-muted-foreground mb-3">
        <span>Agent: {approval.agent_key}</span>
        <span className="mx-1">&middot;</span>
        <span>Venture: {approval.venture_key}</span>
      </div>

      {approval.expires_at && isPending && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground mb-3">
          <Clock className="h-3 w-3" />
          <span>Expires: {new Date(approval.expires_at).toLocaleString()}</span>
        </div>
      )}

      {isPending && (onApprove || onReject) && (
        <div className="flex gap-2">
          {onApprove && (
            <button
              onClick={() => onApprove(approval.id)}
              className="flex-1 rounded-lg bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400 hover:bg-emerald-500/20 transition-colors"
            >
              Approve
            </button>
          )}
          {onReject && (
            <button
              onClick={() => onReject(approval.id)}
              className="flex-1 rounded-lg bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 hover:bg-red-500/20 transition-colors"
            >
              Reject
            </button>
          )}
        </div>
      )}
    </div>
  )
}
