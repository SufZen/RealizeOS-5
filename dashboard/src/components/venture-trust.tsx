/**
 * One venture's effective trust after its packs and firm overrides (spec 010 §3.1).
 *
 * Shows, per action, the trust ladder's decision, the one that applies and
 * the pack or firm default that tightened it, plus the defaults that were
 * ignored because they would loosen trust. Words follow the dashboard's
 * language; codes and pack ids are isolated (`<bdi>`) so they read
 * correctly inside Hebrew text, and the layout uses logical sides only.
 */
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import {
  decisionText,
  decisionTone,
  ignoredDefaults,
  layerText,
  TRUST_COPY,
  trustLang,
  type TrustRow,
  type TrustSource,
  type VentureTrust,
} from '@/lib/trust-copy'

function SourceText({ source, language }: { source: TrustSource; language: string }) {
  const lang = trustLang(language)
  return (
    <span>
      {layerText(source.layer, lang)}
      {source.pack && (
        <>
          {' '}
          <bdi dir="ltr" className="font-mono text-xs">
            {source.pack}
          </bdi>
        </>
      )}
    </span>
  )
}

function Decision({ decision, language }: { decision: string; language: string }) {
  return (
    <Badge tone={decisionTone(decision)} data-decision={decision}>
      {decisionText(decision, trustLang(language))}
    </Badge>
  )
}

function Row({ row, language }: { row: TrustRow; language: string }) {
  const copy = TRUST_COPY[trustLang(language)]
  return (
    <tr data-tightened={row.tightened || undefined}>
      <td>
        <bdi dir="ltr" className="font-mono text-xs">
          {row.action}
        </bdi>
        {row.governed_by && (
          <span className="block text-xs text-muted-foreground">
            {copy.governedBy}{' '}
            <bdi dir="ltr" className="font-mono">
              {row.governed_by}
            </bdi>
          </span>
        )}
      </td>
      <td>
        <Decision decision={row.ladder} language={language} />
      </td>
      <td>
        <Decision decision={row.effective} language={language} />
      </td>
      <td>
        {row.source ? (
          <SourceText source={row.source} language={language} />
        ) : (
          <span className="text-muted-foreground">{copy.ladderOnly}</span>
        )}
      </td>
    </tr>
  )
}

/** The effective trust of one venture: tightened actions first, every action on request. */
export function VentureTrustPanel({
  venture,
  language,
  showAll: initialShowAll = false,
}: {
  venture: VentureTrust
  language: string
  /** Start with every action shown (tests, print). */
  showAll?: boolean
}) {
  const lang = trustLang(language)
  const copy = TRUST_COPY[lang]
  const [showAll, setShowAll] = useState(initialShowAll)
  const tightened = venture.actions.filter((r) => r.tightened)
  const rows = showAll ? venture.actions : tightened
  const ignored = ignoredDefaults(venture.actions)
  const packs = venture.layers.filter((l) => l.pack)

  return (
    <Panel
      title={copy.title(venture.name)}
      flush
      actions={
        <Button
          variant="ghost"
          size="sm"
          aria-pressed={showAll}
          onClick={() => setShowAll(!showAll)}
        >
          {showAll ? copy.showTightened : copy.showAll}
        </Button>
      }
    >
      <div className="grid gap-2 px-4 py-3">
        <p className="text-xs text-muted-foreground">{copy.intro}</p>
        {packs.length > 0 && (
          <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>{copy.packsInUse}:</span>
            {packs.map((l) => (
              <Badge key={`${l.layer}:${l.pack}`} tone="info" outline>
                {layerText(l.layer, lang)}{' '}
                <bdi dir="ltr" className="font-mono">
                  {l.pack}
                </bdi>
              </Badge>
            ))}
          </p>
        )}
      </div>

      {rows.length > 0 ? (
        <table className="rz-table">
          <thead>
            <tr>
              <th scope="col">{copy.columns.action}</th>
              <th scope="col">{copy.columns.ladder}</th>
              <th scope="col">{copy.columns.effective}</th>
              <th scope="col">{copy.columns.source}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <Row key={row.action} row={row} language={language} />
            ))}
          </tbody>
        </table>
      ) : (
        <p className="px-4 pb-3 text-sm text-muted-foreground">{copy.noneTightened}</p>
      )}

      {ignored.length > 0 && (
        <div role="note" className="grid gap-1 border-t border-border px-4 py-3">
          <p className="flex items-center gap-2 text-sm font-medium">
            <Badge tone="warning" dot>
              {copy.warningsTitle}
            </Badge>
          </p>
          <ul className="grid gap-1 text-xs text-muted-foreground">
            {ignored.map((item) => (
              <li key={[item.layer, item.pack, item.key, item.value, item.reason].join('|')}>
                <SourceText source={item} language={language} />:{' '}
                <bdi dir="ltr" className="font-mono">
                  {item.key} = {item.value}
                </bdi>{' '}
                {item.reason === 'invalid' ? copy.invalid : copy.loosen}. {copy.ignoredSuffix}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Panel>
  )
}
