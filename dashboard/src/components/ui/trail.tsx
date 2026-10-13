import type { ReactNode } from 'react'

export type TrailState = 'done' | 'running' | 'held' | 'failed' | 'pending'

export interface TrailStep {
  id: string
  state: TrailState
  title: ReactNode
  meta?: ReactNode
  /** Mark steps that arrived after first render so they slide in. */
  fresh?: boolean
}

/**
 * What an agent did and where each figure came from, drawn as a dashed leader
 * line with a node per step, like the leaders that tie a note to a detail on a
 * drawing. Done is filled green, running breathes, held is a yellow diamond.
 */
export function Trail({ steps, label = 'What I used' }: { steps: TrailStep[]; label?: string }) {
  return (
    <ol className="rz-trail" aria-label={label}>
      {steps.map((s) => (
        <li
          key={s.id}
          className={s.fresh ? 'rz-trail__step rz-trail__step--new' : 'rz-trail__step'}
          data-state={s.state}
          aria-current={s.state === 'running' ? 'step' : undefined}
        >
          <div className="rz-trail__title">{s.title}</div>
          {s.meta && <div className="rz-trail__meta">{s.meta}</div>}
        </li>
      ))}
    </ol>
  )
}

/** The [S1] footnote that ties a figure to the document it came from. */
export function SourceRef({ n, title, onOpen }: { n: number; title: string; onOpen?: () => void }) {
  return (
    <button
      type="button"
      className="rz-source"
      aria-label={`Source ${n}: ${title}`}
      data-tip={title}
      onClick={onOpen}
    >
      S{n}
    </button>
  )
}
