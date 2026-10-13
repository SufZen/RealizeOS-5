import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface PanelProps extends Omit<HTMLAttributes<HTMLElement>, 'title'> {
  title?: ReactNode
  /** Small controls on the far side of the header. */
  actions?: ReactNode
  footer?: ReactNode
  /** Waiting for a person: draws the caution hatch on the leading edge. */
  held?: boolean
  /** No body padding, for tables and lists that run edge to edge. */
  flush?: boolean
}

/** A titled surface. Panels group things; they don't decorate. Don't nest them. */
export function Panel({
  title,
  actions,
  footer,
  held,
  flush,
  className,
  children,
  ...props
}: PanelProps) {
  return (
    <section className={cn('rz-panel', held && 'rz-held', className)} {...props}>
      {(title || actions) && (
        <header className="rz-panel__head">
          {title && <h3 className="rz-panel__title">{title}</h3>}
          {actions && <div className="rz-panel__actions">{actions}</div>}
        </header>
      )}
      <div className={flush ? undefined : 'rz-panel__body'}>{children}</div>
      {footer && <footer className="rz-panel__foot">{footer}</footer>}
    </section>
  )
}
