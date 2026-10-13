/**
 * The trust matrix with packs (spec 010 §3.1), in English and Hebrew.
 *
 * `GET /api/trust` with `features.packs` on adds, per venture and action, the
 * trust ladder's decision, the effective one and the pack or firm default
 * that tightened it. Packs only tighten trust: a default that would loosen a
 * decision is ignored, and the matrix lists it as a warning. docs/packs.md
 * and docs/api-reference.md#trust describe the same fields.
 */
import type { Tone } from '@/components/ui/badge'

export type TrustDecision = 'auto' | 'approve' | 'block'

/** One layer's trust default for one key. */
export interface TrustSource {
  layer: 'firm' | 'market' | 'profession' | string
  /** `id@version`; null for the firm's own overrides. */
  pack: string | null
  key: string
  value: string
  /** The server's English label, e.g. "market pack pt@0.1.0". */
  label: string
}

export interface IgnoredSource extends TrustSource {
  /** `loosen`: it would loosen the ladder's decision. `invalid`: not a trust level. */
  reason: 'loosen' | 'invalid' | string
}

export interface TrustRow {
  action: string
  /** The governance action a tool action falls under (`data_write`), or null. */
  governed_by: string | null
  ladder: TrustDecision | string
  effective: TrustDecision | string
  tightened: boolean
  source: TrustSource | null
  ignored: IgnoredSource[]
}

export interface VentureTrust {
  name: string
  layers: { layer: string; pack: string | null }[]
  actions: TrustRow[]
  warnings: string[]
}

export type TrustLang = 'en' | 'he'

/** Hebrew for Hebrew, English otherwise. */
export function trustLang(language: string): TrustLang {
  return language === 'he' ? 'he' : 'en'
}

export interface TrustCopy {
  title: (venture: string) => string
  intro: string
  columns: { action: string; ladder: string; effective: string; source: string }
  decisions: Record<TrustDecision, string>
  /** Words before a pack id, per layer. The firm has no pack id. */
  layers: Record<string, string>
  /** Before the governance action a tool action falls under. */
  governedBy: string
  noneTightened: string
  showAll: string
  showTightened: string
  ladderOnly: string
  warningsTitle: string
  loosen: string
  invalid: string
  ignoredSuffix: string
  packsInUse: string
}

export const TRUST_COPY: Record<TrustLang, TrustCopy> = {
  en: {
    title: (venture) => `Packs and firm rules · ${venture}`,
    intro:
      'Packs can only make trust stricter. Where a pack or your firm tightened an action, the source is shown.',
    columns: {
      action: 'Action',
      ladder: 'Trust ladder',
      effective: 'Applies',
      source: 'Tightened by',
    },
    decisions: { auto: 'Automatic', approve: 'Needs approval', block: 'Blocked' },
    layers: { firm: 'firm overrides', market: 'market pack', profession: 'profession pack' },
    governedBy: 'falls under',
    noneTightened: 'No pack or firm default tightens this venture’s trust at this level.',
    showAll: 'Show every action',
    showTightened: 'Show tightened only',
    ladderOnly: 'trust ladder',
    warningsTitle: 'Ignored defaults',
    loosen: 'would loosen the trust ladder',
    invalid: 'isn’t a trust level',
    ignoredSuffix: 'Ignored: packs only tighten trust.',
    packsInUse: 'Layers',
  },
  he: {
    title: (venture) => `חבילות וכללי המשרד · ${venture}`,
    intro: 'חבילות יכולות רק להחמיר את רמת האמון. כשחבילה או המשרד החמירו פעולה, המקור מוצג.',
    columns: {
      action: 'פעולה',
      ladder: 'סולם האמון',
      effective: 'בפועל',
      source: 'הוחמר על ידי',
    },
    decisions: { auto: 'אוטומטי', approve: 'דורש אישור', block: 'חסום' },
    layers: { firm: 'הגדרות המשרד', market: 'חבילת שוק', profession: 'חבילת מקצוע' },
    governedBy: 'שייך לקטגוריה',
    noneTightened: 'אף חבילה או הגדרת משרד לא מחמירות את רמת האמון של המיזם ברמה הזו.',
    showAll: 'הצג את כל הפעולות',
    showTightened: 'הצג רק פעולות שהוחמרו',
    ladderOnly: 'סולם האמון',
    warningsTitle: 'הגדרות שנדחו',
    loosen: 'הייתה מקלה על סולם האמון',
    invalid: 'אינה רמת אמון',
    ignoredSuffix: 'נדחתה: חבילות רק מחמירות.',
    packsInUse: 'שכבות',
  },
}

/** Badge tone for a decision: blocked is a redline, approval is held for a person, auto is grey. */
export function decisionTone(decision: string): Tone {
  if (decision === 'block') return 'danger'
  if (decision === 'approve') return 'accent'
  return 'neutral'
}

/** The words for a decision, or the raw value when it isn't one. */
export function decisionText(decision: string, lang: TrustLang): string {
  return TRUST_COPY[lang].decisions[decision as TrustDecision] ?? decision
}

/** Words before a layer's pack id ("market pack"), in the language; the raw layer when unknown. */
export function layerText(layer: string, lang: TrustLang): string {
  return TRUST_COPY[lang].layers[layer] ?? layer
}

/** Every ignored default once, across the venture's rows. */
export function ignoredDefaults(rows: TrustRow[]): IgnoredSource[] {
  const seen = new Set<string>()
  const out: IgnoredSource[] = []
  for (const row of rows) {
    for (const item of row.ignored) {
      const id = [item.layer, item.pack, item.key, item.value, item.reason].join('|')
      if (seen.has(id)) continue
      seen.add(id)
      out.push(item)
    }
  }
  return out
}
