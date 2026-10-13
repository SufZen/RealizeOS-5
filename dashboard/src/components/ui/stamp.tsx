import { cn } from '@/lib/utils'

export type Decision = 'approved' | 'rejected' | 'held'

const WORDS: Record<Decision, string> = {
  approved: 'Approved',
  rejected: 'Rejected',
  held: 'Held',
}

/**
 * The decision mark on an approval. `strike` plays the stamp coming down;
 * set it only at the moment the decision lands, never on page load.
 */
export function Stamp({
  decision,
  by,
  strike,
  className,
}: {
  decision: Decision
  /** Who decided and when, printed small under the word: "Dana · 14:02". */
  by?: string
  strike?: boolean
  className?: string
}) {
  return (
    <span
      role="img"
      aria-label={by ? `${WORDS[decision]}, ${by}` : WORDS[decision]}
      className={cn(
        'rz-stamp',
        decision !== 'approved' && `rz-stamp--${decision}`,
        strike && 'rz-stamp--strike',
        className,
      )}
    >
      {WORDS[decision]}
      {by && <small>{by}</small>}
    </span>
  )
}
