import { FileText } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { sourceAnchorId, toolRows, type ToolStatus, type Trail } from '@/lib/chat-stream'

/** Tool status → trail node state (drawn by .rz-trail__step[data-state]) and its words. */
const STATUS: Record<ToolStatus, { label: string; node: string }> = {
  running: { label: 'running', node: 'running' },
  done: { label: 'done', node: 'done' },
  failed: { label: 'failed', node: 'failed' },
  held: { label: 'waiting for approval', node: 'held' },
}

/**
 * "What I used": the sources an answer read and the tools it called, in
 * order, drawn as a leader line like the ones that tie a note to a detail
 * on a drawing. Live while the answer is being prepared, then stored with it.
 */
export function TrailPanel({ trail, anchorPrefix }: { trail: Trail; anchorPrefix: string }) {
  const navigate = useNavigate()
  const rows = toolRows(trail.steps)
  if (!trail.sources.length && !rows.length) return null

  return (
    // Follows the page direction; mixed-direction pieces are isolated with <bdi>.
    <div className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
      <div className="mb-1.5 text-xs font-medium text-subtle-foreground">What I used</div>

      {trail.sources.length > 0 && (
        <ol className="m-0 grid list-none gap-1 p-0">
          {trail.sources.map((s) => (
            <li
              key={s.id}
              id={sourceAnchorId(anchorPrefix, s.id)}
              className="flex min-w-0 items-center gap-2 scroll-mt-4 rounded-[5px] target:bg-blue-400/10"
            >
              <span className="rz-source m-0" aria-hidden>
                {s.id}
              </span>
              <FileText className="h-3.5 w-3.5 shrink-0" />
              <bdi className="text-foreground">{s.title}</bdi>
              <bdi className="min-w-0 truncate text-subtle-foreground" title={s.path}>
                {s.path}
              </bdi>
            </li>
          ))}
        </ol>
      )}

      {rows.length > 0 && (
        <ol className={cn('rz-trail m-0 list-none p-0', trail.sources.length > 0 && 'mt-2')}>
          {rows.map((row) => {
            const status = STATUS[row.status]
            return (
              <li
                key={row.id}
                className="rz-trail__step py-1"
                data-state={status.node}
                aria-current={row.status === 'running' ? 'step' : undefined}
              >
                <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
                  <bdi className="font-mono text-foreground">{row.name}</bdi>
                  {row.status === 'held' ? (
                    <button
                      type="button"
                      onClick={() => navigate('/approvals', { viewTransition: true })}
                      className="font-medium text-brand-400 hover:underline"
                    >
                      {status.label}
                    </button>
                  ) : (
                    <span
                      className={cn(
                        row.status === 'failed' && 'text-red-400',
                        row.status === 'running' && 'text-violet-400',
                      )}
                    >
                      {status.label}
                    </span>
                  )}
                  {row.durationMs !== undefined && row.status === 'done' && (
                    <bdi className="tabular text-subtle-foreground">
                      {Math.round(row.durationMs)} ms
                    </bdi>
                  )}
                  {row.status === 'failed' && row.error && (
                    <bdi className="min-w-0 truncate text-red-400/80" title={row.error}>
                      {row.error}
                    </bdi>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
