import { cloneElement, isValidElement, useId, type ReactElement, type ReactNode } from 'react'
import { AlertCircle } from 'lucide-react'

/**
 * Label + control + help or error, wired for screen readers. Pass a single
 * input-like element as the child; it receives id, aria-describedby and
 * aria-invalid.
 */
export function Field({
  label,
  help,
  error,
  children,
}: {
  label: ReactNode
  help?: ReactNode
  error?: ReactNode
  children: ReactElement<Record<string, unknown>>
}) {
  const id = useId()
  const noteId = `${id}-note`
  const control = isValidElement(children)
    ? cloneElement(children, {
        id,
        'aria-describedby': help || error ? noteId : undefined,
        'aria-invalid': error ? true : undefined,
      })
    : children
  return (
    <div className="rz-field">
      <label htmlFor={id} className="rz-label">
        {label}
      </label>
      {control}
      {error ? (
        <span id={noteId} className="rz-error" role="alert">
          <AlertCircle className="h-3.5 w-3.5" aria-hidden />
          {error}
        </span>
      ) : (
        help && (
          <span id={noteId} className="rz-help">
            {help}
          </span>
        )
      )}
    </div>
  )
}
