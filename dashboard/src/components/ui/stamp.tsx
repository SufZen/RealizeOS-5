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
  label,
  className,
}: {
  decision: Decision
  /** Who decided and when, printed small under the word: "Dana · 14:02". */
  by?: string
  strike?: boolean
  /** The word in the person's language ("אושר"); English by default. */
  label?: string
  className?: string
}) {
  const word = label || WORDS[decision]
  return (
    <span
      role="img"
      aria-label={by ? `${word}, ${by}` : word}
      className={cn(
        'rz-stamp',
        decision !== 'approved' && `rz-stamp--${decision}`,
        strike && 'rz-stamp--strike',
        className,
      )}
    >
      {word}
      {by && <small>{by}</small>}
    </span>
  )
}
