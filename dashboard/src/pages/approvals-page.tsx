import { useState } from 'react'
import { ShieldCheck, AlertCircle, RefreshCw } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { ApprovalCard, type Approval } from '@/components/approval-card'
import { api } from '@/lib/api'

interface ApprovalsResponse {
  approvals: Approval[]
}

export default function ApprovalsPage() {
  const { data, loading, error, refetch } = useApi<ApprovalsResponse>('/approvals?status=pending')
  const [noteMap, setNoteMap] = useState<Record<string, string>>({})

  async function handleApprove(id: string) {
    await api.post(`/approvals/${id}/approve`, { decision_note: noteMap[id] || null })
    refetch()
  }

  async function handleReject(id: string) {
    await api.post(`/approvals/${id}/reject`, { decision_note: noteMap[id] || null })
    refetch()
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading approvals...</div>
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    )
  }

  const approvals = data?.approvals ?? []

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Approvals</h1>
          {approvals.length > 0 && (
            <span className="text-xs bg-brand-400/10 text-brand-400 px-2 py-0.5 rounded-full font-medium">
              {approvals.length} pending
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

      {approvals.length === 0 ? (
        <div className="text-center py-16">
          <ShieldCheck className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
          <p className="text-muted-foreground">No pending approvals</p>
          <p className="text-xs text-muted-foreground/70 mt-1">
            Approvals appear here when agents attempt gated actions
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {approvals.map((approval) => (
            <div key={approval.id} className="space-y-2">
              <ApprovalCard
                approval={approval}
                onApprove={handleApprove}
                onReject={handleReject}
              />
              <input
                type="text"
                placeholder="Optional note..."
                value={noteMap[approval.id] || ''}
                onChange={(e) => setNoteMap((m) => ({ ...m, [approval.id]: e.target.value }))}
                className="w-full rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
