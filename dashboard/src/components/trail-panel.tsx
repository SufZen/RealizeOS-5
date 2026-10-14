import { AlertTriangle, FileText, Scale } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Badge } from '@/components/ui/badge'
import { useLocale } from '@/components/locale-provider'
import { cn } from '@/lib/utils'
import {
  isRuleSource,
  sourceAnchorId,
  toolRows,
  trailNotices,
  type ToolStatus,
  type Trail,
  type TrailSource,
} from '@/lib/chat-stream'
import { noticeLine } from '@/lib/llm-settings-text'
import { levelLabel, TRAIL_COPY, trailLang, type TrailLang } from '@/lib/trail-copy'

/** Tool status → trail node state, drawn by .rz-trail__step[data-state]. */
const NODE: Record<ToolStatus, string> = {
  running: 'running',
  done: 'done',
  failed: 'failed',
  held: 'held',
}

/** Only web links open; anything else in a pack's `source` stays text. */
function webLink(path: string): string | undefined {
  return /^https?:\/\//i.test(path) ? path : undefined
}

/** A KB source: number, title and file path on one line. */
function PlainSourceRow({ source, anchorId }: { source: TrailSource; anchorId: string }) {
  return (
    <li
      id={anchorId}
      className="flex min-w-0 items-center gap-2 scroll-mt-4 rounded-[5px] target:bg-blue-400/10"
    >
      <span className="rz-source m-0" aria-hidden>
        {source.id}
      </span>
      <FileText className="h-3.5 w-3.5 shrink-0" />
      <bdi className="text-foreground">{source.title}</bdi>
      <bdi className="min-w-0 truncate text-subtle-foreground" title={source.path}>
        {source.path}
      </bdi>
    </li>
  )
}

/**
 * A rule card: its statement, then its verification level in words, the
 * layer and pack it came from, its as-of date and its source link.
 */
function RuleSourceRow({
  source,
  anchorId,
  lang,
}: {
  source: TrailSource
  anchorId: string
  lang: TrailLang
}) {
  const copy = TRAIL_COPY[lang]
  const level = levelLabel(source, lang)
  const href = webLink(source.path)
  return (
    <li
      id={anchorId}
      className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-start gap-x-2 gap-y-1 scroll-mt-4 rounded-[5px] target:bg-blue-400/10"
    >
      <span className="rz-source m-0" aria-hidden>
        {source.id}
      </span>
      <div className="flex min-w-0 items-center gap-2">
        <Scale className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <bdi className="min-w-0 text-foreground">{source.title}</bdi>
      </div>
      <div className="col-start-2 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        {level && (
          <Badge tone={level.tone} data-level={source.verification ?? 'none'}>
            {level.text}
          </Badge>
        )}
        {source.layer && (
          <span className="inline-flex items-center gap-1">
            {copy.layers[source.layer] ?? source.layer}
            {source.pack && (
              <bdi dir="ltr" className="font-mono text-subtle-foreground">
                {source.pack}
              </bdi>
            )}
          </span>
        )}
        {source.as_of && (
          <bdi
            className="tabular"
            title={source.review_by ? copy.reviewBy(source.review_by) : undefined}
          >
            {copy.asOf(source.as_of)}
          </bdi>
        )}
        {href ? (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="min-w-0 truncate text-subtle-foreground hover:underline"
            title={source.path}
          >
            <bdi>{source.path}</bdi>
          </a>
        ) : (
          source.path && (
            <bdi className="min-w-0 truncate text-subtle-foreground" title={source.path}>
              {source.path}
            </bdi>
          )
        )}
      </div>
    </li>
  )
}

/** Rule cards, and any source that arrives with provenance, show it. */
function hasProvenance(source: TrailSource): boolean {
  return isRuleSource(source) || source.verification !== undefined || source.layer !== undefined
}

/**
 * "What I used": the sources an answer read and the tools it called, in
 * order, drawn as a leader line like the ones that tie a note to a detail
 * on a drawing. Live while the answer is being prepared, then stored with it.
 * Every rule card shows its verification level, whatever the answer says.
 */
export function TrailPanel({ trail, anchorPrefix }: { trail: Trail; anchorPrefix: string }) {
  const navigate = useNavigate()
  const { language } = useLocale()
  const lang = trailLang(language)
  const copy = TRAIL_COPY[lang]
  const rows = toolRows(trail.steps)
  const notices = trailNotices(trail.steps)
  if (!trail.sources.length && !rows.length && !notices.length) return null

  return (
    // Follows the page direction; mixed-direction pieces are isolated with <bdi>.
    <div className="mt-3 border-t border-border pt-3 text-xs text-muted-foreground">
      <div className="mb-1.5 text-xs font-medium text-subtle-foreground">{copy.heading}</div>

      {trail.sources.length > 0 && (
        <ol className="m-0 grid list-none gap-1 p-0">
          {trail.sources.map((s) => {
            const anchorId = sourceAnchorId(anchorPrefix, s.id)
            return hasProvenance(s) ? (
              <RuleSourceRow key={s.id} source={s} anchorId={anchorId} lang={lang} />
            ) : (
              <PlainSourceRow key={s.id} source={s} anchorId={anchorId} />
            )
          })}
        </ol>
      )}

      {notices.length > 0 && (
        <ul
          className={cn('m-0 grid list-none gap-1 p-0', trail.sources.length > 0 && 'mt-2')}
          data-trail="notices"
        >
          {notices.map((n, i) => (
            <li key={i} role="status" className="flex items-start gap-2 text-amber-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="min-w-0">{noticeLine(n, language)}</span>
            </li>
          ))}
        </ul>
      )}

      {rows.length > 0 && (
        <ol
          className={cn(
            'rz-trail m-0 list-none p-0',
            (trail.sources.length > 0 || notices.length > 0) && 'mt-2',
          )}
        >
          {rows.map((row) => {
            const label = copy.status[row.status]
            return (
              <li
                key={row.id}
                className="rz-trail__step py-1"
                data-state={NODE[row.status]}
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
                      {label}
                    </button>
                  ) : (
                    <span
                      className={cn(
                        row.status === 'failed' && 'text-red-400',
                        row.status === 'running' && 'text-violet-400',
                      )}
                    >
                      {label}
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
