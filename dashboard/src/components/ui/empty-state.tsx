import type { ReactNode } from 'react'

export type EmptyArt = 'approvals' | 'documents' | 'activity' | 'search'

/**
 * Line-art schematics in the site's illustration language: amber stroke,
 * opacity does the layering, dashed connectors, drawn on when they appear.
 */
function Art({ kind }: { kind: EmptyArt }) {
  const common = {
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
  }
  return (
    <svg viewBox="0 0 200 140" className="rz-empty__art" aria-hidden>
      {/* drawing sheet with title block */}
      <rect x="40" y="16" width="120" height="100" rx="4" {...common} strokeOpacity={0.3} />
      <path d="M40 98h120M118 98v18" {...common} strokeOpacity={0.2} />
      {kind === 'approvals' && (
        <>
          <path d="M58 40h56M58 52h40M58 64h48" {...common} strokeOpacity={0.25} />
          <g transform="rotate(-8 132 60)">
            <rect x="110" y="46" width="44" height="26" rx="3" {...common} strokeOpacity={0.6} />
            <path
              d="M120 59l6 6 12-12"
              {...common}
              strokeOpacity={0.6}
              strokeDasharray="30"
              style={{
                animation: 'rz-draw 700ms var(--rz-ease-out) 200ms both',
                ['--rz-draw-length' as string]: 30,
              }}
            />
          </g>
        </>
      )}
      {kind === 'documents' && (
        <>
          <rect x="58" y="32" width="36" height="46" rx="2" {...common} strokeOpacity={0.4} />
          <rect
            x="70"
            y="40"
            width="36"
            height="46"
            rx="2"
            {...common}
            strokeOpacity={0.6}
            fill="currentColor"
            fillOpacity={0.06}
          />
          <path d="M78 54h20M78 62h14" {...common} strokeOpacity={0.4} />
          <path d="M112 64h28" {...common} strokeOpacity={0.3} strokeDasharray="3 3" />
          <circle cx="144" cy="64" r="3" {...common} strokeOpacity={0.5} />
        </>
      )}
      {kind === 'activity' && (
        <>
          <path
            d="M56 70h18l8-18 12 34 10-24 8 8h32"
            {...common}
            strokeOpacity={0.6}
            strokeDasharray="160"
            style={{
              animation: 'rz-draw 900ms var(--rz-ease-out) both',
              ['--rz-draw-length' as string]: 160,
            }}
          />
          <path d="M56 84h88" {...common} strokeOpacity={0.15} strokeDasharray="3 3" />
        </>
      )}
      {kind === 'search' && (
        <>
          <circle cx="94" cy="56" r="18" {...common} strokeOpacity={0.6} />
          <path d="M107 69l14 14" {...common} strokeOpacity={0.6} />
          <path d="M60 36h16M60 44h10" {...common} strokeOpacity={0.2} />
        </>
      )}
      <path d="M124 104h28M124 109h18" {...common} strokeOpacity={0.2} />
    </svg>
  )
}

/** An empty screen is an invitation: say what goes here and the one way to start. */
export function EmptyState({
  art = 'documents',
  title,
  body,
  action,
}: {
  art?: EmptyArt
  title: ReactNode
  body?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="rz-empty">
      <Art kind={art} />
      <h3 className="rz-empty__title">{title}</h3>
      {body && <p className="rz-empty__body">{body}</p>}
      {action}
    </div>
  )
}
