import { CheckCircle2, Clock, FileText, Loader2, Wrench, XCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { sourceAnchorId, toolRows, type ToolStatus, type Trail } from '@/lib/chat-stream'

const STATUS: Record<ToolStatus, { label: string; icon: typeof CheckCircle2; className: string }> =
  {
    running: { label: 'running', icon: Loader2, className: 'text-muted-foreground animate-spin' },
    done: { label: 'done', icon: CheckCircle2, className: 'text-emerald-400' },
    failed: { label: 'failed', icon: XCircle, className: 'text-red-400' },
    held: { label: 'waiting for approval', icon: Clock, className: 'text-brand-400' },
  }

/**
 * "What I used": the sources an answer read and the tools it called, in
 * order. Live while the answer is being prepared, then stored with it.
 */
export function TrailPanel({ trail, anchorPrefix }: { trail: Trail; anchorPrefix: string }) {
  const navigate = useNavigate()
  const rows = toolRows(trail.steps)
  if (!trail.sources.length && !rows.length) return null

  return (
    <div className="mt-3 border-t border-border pt-2 text-xs text-muted-foreground" dir="auto">
      <div className="mb-1 font-medium uppercase tracking-wider text-[10px]">What I used</div>

      {trail.sources.length > 0 && (
        <ol className="space-y-0.5">
          {trail.sources.map((s) => (
            <li
              key={s.id}
              id={sourceAnchorId(anchorPrefix, s.id)}
              className="flex items-baseline gap-1.5 scroll-mt-4"
            >
              <span className="font-mono text-brand-400">[{s.id}]</span>
              <FileText className="h-3 w-3 shrink-0 self-center" />
              <span className="text-foreground">{s.title}</span>
              <span className="truncate opacity-60" title={s.path}>
                {s.path}
              </span>
            </li>
          ))}
        </ol>
      )}

      {rows.length > 0 && (
        <ul className={cn('space-y-0.5', trail.sources.length > 0 && 'mt-1.5')}>
          {rows.map((row) => {
            const status = STATUS[row.status]
            const Icon = status.icon
            return (
              <li key={row.id} className="flex items-center gap-1.5">
                <Wrench className="h-3 w-3 shrink-0" />
                <span className="font-mono text-foreground">{row.name}</span>
                <Icon className={cn('h-3 w-3 shrink-0', status.className)} aria-hidden />
                {row.status === 'held' ? (
                  <button
                    type="button"
                    onClick={() => navigate('/approvals')}
                    className="text-brand-400 hover:underline"
                  >
                    {status.label}
                  </button>
                ) : (
                  <span>{status.label}</span>
                )}
                {row.durationMs !== undefined && row.status === 'done' && (
                  <span className="opacity-60">{Math.round(row.durationMs)} ms</span>
                )}
                {row.status === 'failed' && row.error && (
                  <span className="truncate text-red-400/80" title={row.error}>
                    {row.error}
                  </span>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
