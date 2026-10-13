import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

export interface Crumb {
  label: string
  to?: string
}

interface TitleBlockProps {
  title: ReactNode
  description?: ReactNode
  crumbs?: Crumb[]
  /** Scope cells, like a drawing's sheet reference: venture, project, revision. */
  reference?: string[]
  actions?: ReactNode
}

/**
 * The page header, modelled on a drawing sheet's title block: where you are,
 * what this sheet is, what scope it covers, and what you can do here.
 */
export function TitleBlock({ title, description, crumbs, reference, actions }: TitleBlockProps) {
  return (
    <header className="rz-title-block">
      {crumbs && crumbs.length > 0 && (
        <nav className="rz-title-block__crumbs" aria-label="Breadcrumb">
          {crumbs.map((c, i) => (
            <span key={c.label} className="inline-flex items-center gap-1.5">
              {i > 0 && <ChevronRight className="h-3 w-3 opacity-60 rtl:rotate-180" aria-hidden />}
              {c.to ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div>
        <h1 className="rz-title-block__title">{title}</h1>
        {description && <p className="rz-title-block__desc">{description}</p>}
      </div>
      {(actions || (reference && reference.length > 0)) && (
        <div className="rz-title-block__actions">
          {reference && reference.length > 0 && (
            <span className="rz-title-block__ref">
              {reference.map((r) => (
                <span key={r}>{r}</span>
              ))}
            </span>
          )}
          {actions}
        </div>
      )}
    </header>
  )
}
