import { useState, useMemo } from 'react'
import {
  Sparkles,
  CheckCircle2,
  XCircle,
  Clock,
  RefreshCw,
  ChevronRight,
  Tag,
  Link2,
  AlertTriangle,
  Lightbulb,
  Shield,
  FileText,
  Zap,
  BarChart3,
  Filter,
  Archive,
} from 'lucide-react'
import { cn } from '@/lib/utils'

/* ─── Types ──────────────────────────────────────────────────────── */

interface DreamProposal {
  proposal_id: string
  cycle_type: string
  action: string
  entity_id: string
  entity_type: string
  venture: string
  title: string
  description: string
  diff: Record<string, unknown>
  confidence: number
  rationale: string
  evidence: string[]
  status: string
  created_at: string
  reviewed_at: string | null
  reviewed_by: string
  rejection_reason: string
}

/* ─── Status config ──────────────────────────────────────────────── */

const statusConfig: Record<string, { icon: typeof Clock; color: string; label: string }> = {
  pending: { icon: Clock, color: 'text-amber-400 bg-amber-400/10', label: 'Pending' },
  approved: { icon: CheckCircle2, color: 'text-emerald-400 bg-emerald-400/10', label: 'Approved' },
  rejected: { icon: XCircle, color: 'text-red-400 bg-red-400/10', label: 'Rejected' },
  applied: { icon: CheckCircle2, color: 'text-blue-400 bg-blue-400/10', label: 'Applied' },
  expired: { icon: Archive, color: 'text-gray-500 bg-gray-500/10', label: 'Expired' },
}

const actionConfig: Record<string, { icon: typeof Tag; color: string }> = {
  add_tag: { icon: Tag, color: 'text-emerald-400' },
  add_ref: { icon: Link2, color: 'text-blue-400' },
  annotate_entity: { icon: FileText, color: 'text-violet-400' },
  update_summary: { icon: FileText, color: 'text-violet-400' },
  flag_stale_commitment: { icon: AlertTriangle, color: 'text-amber-400' },
  flag_orphan: { icon: AlertTriangle, color: 'text-orange-400' },
  update_trust_score: { icon: Shield, color: 'text-cyan-400' },
  suggest_archive: { icon: Archive, color: 'text-gray-400' },
  create_insight: { icon: Lightbulb, color: 'text-yellow-400' },
  create_hypothesis: { icon: Lightbulb, color: 'text-pink-400' },
  merge_entities: { icon: Zap, color: 'text-red-400' },
  suggest_decision: { icon: Zap, color: 'text-amber-400' },
}

const cycleColors: Record<string, string> = {
  reflex: 'text-emerald-400 bg-emerald-400/10',
  curator: 'text-violet-400 bg-violet-400/10',
  synthesis: 'text-amber-400 bg-amber-400/10',
}

/* ─── Confidence bar ─────────────────────────────────────────────── */

function ConfidenceIndicator({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'bg-emerald-400' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-12 h-1.5 rounded-full bg-surface-700 overflow-hidden">
        <div className={cn('h-full rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-muted-foreground font-mono">{pct}%</span>
    </div>
  )
}

/* ─── Proposal card ──────────────────────────────────────────────── */

function ProposalCard({
  proposal,
  onApprove,
  onReject,
}: {
  proposal: DreamProposal
  onApprove: (id: string) => void
  onReject: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const status = statusConfig[proposal.status] || statusConfig.pending
  const action = actionConfig[proposal.action] || { icon: Zap, color: 'text-brand-400' }
  const ActionIcon = action.icon
  const StatusIcon = status.icon
  const isPending = proposal.status === 'pending'
  const cycleColor = cycleColors[proposal.cycle_type] || cycleColors.curator

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card p-4 transition-all duration-200',
        'hover:border-brand-400/30 hover:shadow-lg hover:shadow-brand-400/5',
        isPending && 'border-l-2 border-l-amber-400',
        expanded && 'ring-1 ring-brand-400/20',
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'rounded-lg p-1.5 flex-shrink-0',
            `bg-${action.color.split('-')[1]}-400/10`,
          )}
        >
          <ActionIcon className={cn('h-4 w-4', action.color)} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <h3 className="text-sm font-semibold text-foreground truncate">{proposal.title}</h3>
            <span
              className={cn(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium',
                status.color,
              )}
            >
              <StatusIcon className="h-2.5 w-2.5" />
              {status.label}
            </span>
          </div>

          <p className="text-xs text-muted-foreground line-clamp-2 mb-2">{proposal.description}</p>

          <div className="flex items-center gap-3 text-xs text-muted-foreground flex-wrap">
            <span
              className={cn(
                'px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold',
                cycleColor,
              )}
            >
              {proposal.cycle_type}
            </span>
            <span className="bg-surface-700 px-1.5 py-0.5 rounded">{proposal.action}</span>
            {proposal.entity_id && (
              <span className="font-mono truncate max-w-[150px]">{proposal.entity_id}</span>
            )}
            <ConfidenceIndicator value={proposal.confidence} />
            <span>{new Date(proposal.created_at).toLocaleDateString()}</span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {isPending && (
            <>
              <button
                onClick={() => onApprove(proposal.proposal_id)}
                className="rounded-lg p-1.5 text-emerald-400 hover:bg-emerald-400/10 transition-colors"
                title="Approve"
                aria-label="Approve proposal"
              >
                <CheckCircle2 className="h-4 w-4" />
              </button>
              <button
                onClick={() => onReject(proposal.proposal_id)}
                className="rounded-lg p-1.5 text-red-400 hover:bg-red-400/10 transition-colors"
                title="Reject"
                aria-label="Reject proposal"
              >
                <XCircle className="h-4 w-4" />
              </button>
            </>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="rounded-lg p-1 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            aria-label={expanded ? 'Collapse' : 'Expand'}
          >
            <ChevronRight className={cn('h-4 w-4 transition-transform', expanded && 'rotate-90')} />
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-border space-y-2 text-xs">
          {proposal.rationale && (
            <div>
              <span className="text-muted-foreground font-medium">Rationale:</span>
              <p className="text-foreground mt-0.5">{proposal.rationale}</p>
            </div>
          )}
          {proposal.evidence.length > 0 && (
            <div>
              <span className="text-muted-foreground font-medium">Evidence:</span>
              <ul className="mt-0.5 space-y-0.5">
                {proposal.evidence.map((e, i) => (
                  <li
                    key={i}
                    className="text-foreground font-mono bg-surface-700 px-2 py-0.5 rounded"
                  >
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {proposal.diff && Object.keys(proposal.diff).length > 0 && (
            <div>
              <span className="text-muted-foreground font-medium">Proposed changes:</span>
              <pre className="mt-0.5 bg-surface-700 p-2 rounded text-[10px] overflow-x-auto">
                {JSON.stringify(proposal.diff, null, 2)}
              </pre>
            </div>
          )}
          {proposal.rejection_reason && (
            <div className="text-red-400">
              <span className="font-medium">Rejection reason:</span> {proposal.rejection_reason}
            </div>
          )}
          {proposal.reviewed_at && (
            <div className="text-muted-foreground">
              Reviewed by {proposal.reviewed_by} on{' '}
              {new Date(proposal.reviewed_at).toLocaleString()}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ─── Page ────────────────────────────────────────────────────────── */

export default function DreamInboxPage() {
  const [statusFilter, setStatusFilter] = useState('pending')
  const [cycleFilter, setCycleFilter] = useState('')

  // Mock proposals (the inbox will be API-backed once dream endpoint is exposed)
  const mockProposals: DreamProposal[] = [
    {
      proposal_id: 'dream-ab3f2e1c9d0a',
      cycle_type: 'reflex',
      action: 'add_tag',
      entity_id: 'dec-2026-05-pricing-001',
      entity_type: 'decision',
      venture: 'burtucala',
      title: 'Add pricing tag to Pricing Model Decision',
      description: 'Suggested tags based on content analysis: pricing, strategy',
      diff: { add_tags: ['pricing', 'strategy'] },
      confidence: 0.85,
      rationale: 'Keywords "pricing" and "strategy" found in body content',
      evidence: [],
      status: 'approved',
      created_at: '2026-05-24T08:00:00Z',
      reviewed_at: '2026-05-24T08:00:00Z',
      reviewed_by: 'trust-policy-auto',
      rejection_reason: '',
    },
    {
      proposal_id: 'dream-7f8e2c4b1d3a',
      cycle_type: 'curator',
      action: 'flag_stale_commitment',
      entity_id: 'commitment-2026-05-send-rationale-001',
      entity_type: 'commitment',
      venture: 'burtucala',
      title: 'Overdue commitment: Send rationale to investor',
      description: 'Commitment is 5 day(s) past deadline (2026-05-19)',
      diff: { days_overdue: 5, deadline: '2026-05-19' },
      confidence: 1.0,
      rationale: 'Deadline has passed with status still open',
      evidence: [],
      status: 'pending',
      created_at: '2026-05-24T09:00:00Z',
      reviewed_at: null,
      reviewed_by: '',
      rejection_reason: '',
    },
    {
      proposal_id: 'dream-c1d2e3f4a5b6',
      cycle_type: 'curator',
      action: 'flag_orphan',
      entity_id: 'insight-2026-04-funnel-001',
      entity_type: 'insight',
      venture: 'burtucala',
      title: 'Orphan entity: Funnel Pattern Insight',
      description: 'This entity has no inbound references from other entities',
      diff: {},
      confidence: 0.6,
      rationale: 'Orphan entities may indicate missing connections or stale content',
      evidence: [],
      status: 'pending',
      created_at: '2026-05-24T09:01:00Z',
      reviewed_at: null,
      reviewed_by: '',
      rejection_reason: '',
    },
    {
      proposal_id: 'dream-e5f6a7b8c9d0',
      cycle_type: 'reflex',
      action: 'annotate_entity',
      entity_id: 'dec-2026-05-location-001',
      entity_type: 'decision',
      venture: 'burtucala',
      title: 'Missing status on decision: Office Location',
      description:
        "Decision entity is missing a 'status' field (proposed/committed/deferred/reversed)",
      diff: { suggest_field: 'status', suggested_value: 'proposed' },
      confidence: 0.6,
      rationale: 'All decisions should have a status for tracking',
      evidence: [],
      status: 'pending',
      created_at: '2026-05-24T09:05:00Z',
      reviewed_at: null,
      reviewed_by: '',
      rejection_reason: '',
    },
    {
      proposal_id: 'dream-1a2b3c4d5e6f',
      cycle_type: 'curator',
      action: 'annotate_entity',
      entity_id: 'doc-2026-05-report-001',
      entity_type: 'document',
      venture: 'burtucala',
      title: 'Untagged entity: Monthly Report',
      description: 'Entity has no tags, making it harder to discover',
      diff: {},
      confidence: 0.5,
      rationale: 'Tags improve discoverability and agent context relevance',
      evidence: [],
      status: 'rejected',
      created_at: '2026-05-23T20:00:00Z',
      reviewed_at: '2026-05-24T10:00:00Z',
      reviewed_by: 'user-asaf',
      rejection_reason: 'Not necessary for internal reports',
    },
  ]

  const handleApprove = (id: string) => {
    console.log('Approve:', id)
    // Will call POST /api/fabric/dream/approve/{id}
  }

  const handleReject = (id: string) => {
    console.log('Reject:', id)
    // Will call POST /api/fabric/dream/reject/{id}
  }

  const filteredProposals = useMemo(() => {
    let proposals = mockProposals
    if (statusFilter) {
      proposals = proposals.filter((p) => p.status === statusFilter)
    }
    if (cycleFilter) {
      proposals = proposals.filter((p) => p.cycle_type === cycleFilter)
    }
    return proposals.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, cycleFilter])

  // Stats
  const stats = {
    total: mockProposals.length,
    pending: mockProposals.filter((p) => p.status === 'pending').length,
    approved: mockProposals.filter((p) => p.status === 'approved').length,
    rejected: mockProposals.filter((p) => p.status === 'rejected').length,
  }

  return (
    <div className="space-y-6 rz-animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Dream Inbox</h1>
        </div>
        <div className="flex items-center gap-2">
          {stats.pending > 0 && (
            <span className="text-xs bg-amber-400/10 text-amber-400 px-2.5 py-1 rounded-full font-medium">
              {stats.pending} pending
            </span>
          )}
          <button
            className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            aria-label="Refresh inbox"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total', value: stats.total, icon: BarChart3, color: 'text-brand-400' },
          { label: 'Pending', value: stats.pending, icon: Clock, color: 'text-amber-400' },
          {
            label: 'Approved',
            value: stats.approved,
            icon: CheckCircle2,
            color: 'text-emerald-400',
          },
          { label: 'Rejected', value: stats.rejected, icon: XCircle, color: 'text-red-400' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="rounded-xl border border-border bg-card p-3 fx-glass">
            <div className="flex items-center gap-2 mb-1">
              <Icon className={cn('h-4 w-4', color)} />
              <span className="text-xs text-muted-foreground">{label}</span>
            </div>
            <div className="text-lg font-bold text-foreground">{value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Filter className="h-3.5 w-3.5" />
          <span>Filter:</span>
        </div>
        <div className="flex rounded-lg border border-border bg-surface-800 overflow-hidden">
          {['pending', 'approved', 'rejected', ''].map((s) => (
            <button
              key={s || 'all'}
              onClick={() => setStatusFilter(s)}
              className={cn(
                'px-3 py-1.5 text-xs transition-colors',
                statusFilter === s
                  ? 'bg-brand-400/10 text-brand-400 font-medium'
                  : 'text-muted-foreground hover:text-foreground hover:bg-surface-700',
              )}
            >
              {s ? statusConfig[s]?.label : 'All'}
            </button>
          ))}
        </div>
        <select
          value={cycleFilter}
          onChange={(e) => setCycleFilter(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground',
            'focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        >
          <option value="">All cycles</option>
          <option value="reflex">Reflex</option>
          <option value="curator">Curator</option>
          <option value="synthesis">Synthesis</option>
        </select>
      </div>

      {/* Proposals list */}
      <div className="space-y-2">
        {filteredProposals.map((proposal) => (
          <ProposalCard
            key={proposal.proposal_id}
            proposal={proposal}
            onApprove={handleApprove}
            onReject={handleReject}
          />
        ))}

        {filteredProposals.length === 0 && (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Sparkles className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
            <h3 className="text-sm font-medium text-foreground mb-1">
              {statusFilter === 'pending' ? 'No pending proposals' : 'No proposals found'}
            </h3>
            <p className="text-xs text-muted-foreground">
              {statusFilter === 'pending'
                ? 'The Dreaming subsystem has no proposals awaiting your review.'
                : 'Try adjusting your filters to see more proposals.'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
