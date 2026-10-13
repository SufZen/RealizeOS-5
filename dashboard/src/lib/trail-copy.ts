/**
 * Words for the "What I used" trail, in English and Hebrew (Codex audit N03).
 *
 * A pack rule card ([R1]…) shows its verification level on the ADR 0005
 * ladder in words, beside the layer and pack it came from, on every answer
 * and whatever the model wrote. Level 1 is always called a draft (filter 7,
 * candor). docs/packs.md lists the same words.
 */
import type { Tone } from '@/components/ui/badge'
import { isRuleSource, type ToolStatus, type TrailSource } from './chat-stream'

export type TrailLang = 'en' | 'he'

/** The trail's language: Hebrew for Hebrew, English otherwise. */
export function trailLang(language: string): TrailLang {
  return language === 'he' ? 'he' : 'en'
}

interface TrailCopy {
  heading: string
  /** Words for each verification level, 0-4. */
  levels: Record<number, string>
  level: (n: number) => string
  /** Where a rule came from, before its pack id. */
  layers: Record<string, string>
  asOf: (date: string) => string
  reviewBy: (date: string) => string
  status: Record<ToolStatus, string>
  /** Accessible name of an inline [S1] / [R1] footnote. */
  cite: (marker: string) => string
}

export const TRAIL_COPY: Record<TrailLang, TrailCopy> = {
  en: {
    heading: 'What I used',
    levels: {
      0: 'unverified',
      1: 'draft — not reviewed',
      2: 'reviewed',
      3: 'maintained',
      4: 'field-proven',
    },
    level: (n) => `Level ${n}`,
    layers: {
      firm: 'your firm',
      market: 'market pack',
      profession: 'profession pack',
      core: 'core',
    },
    asOf: (date) => `as of ${date}`,
    reviewBy: (date) => `review by ${date}`,
    status: { running: 'running', done: 'done', failed: 'failed', held: 'waiting for approval' },
    cite: (marker) => (marker.startsWith('R') ? `Rule ${marker}` : `Source ${marker}`),
  },
  he: {
    heading: 'במה השתמשתי',
    levels: {
      0: 'לא מאומת',
      1: 'טיוטה — לא נבדקה',
      2: 'נבדק',
      3: 'מתוחזק',
      4: 'הוכח בשטח',
    },
    level: (n) => `רמה ${n}`,
    layers: {
      firm: 'המשרד שלך',
      market: 'חבילת שוק',
      profession: 'חבילת מקצוע',
      core: 'ליבה',
    },
    asOf: (date) => `נכון ל־${date}`,
    reviewBy: (date) => `לבדיקה עד ${date}`,
    status: { running: 'רץ', done: 'הושלם', failed: 'נכשל', held: 'ממתין לאישור' },
    cite: (marker) => (marker.startsWith('R') ? `כלל ${marker}` : `מקור ${marker}`),
  },
}

export interface LevelLabel {
  tone: Tone
  text: string
}

/**
 * The level badge for a source, or null for a KB source without one.
 *
 * A rule card always gets one. Levels 0-1 read as needing attention; a rule
 * whose level is missing (stored before levels were recorded) or off the
 * ladder reads as unverified, never as more than it is.
 */
export function levelLabel(source: TrailSource, lang: TrailLang): LevelLabel | null {
  const copy = TRAIL_COPY[lang]
  const level = source.verification
  if (level === undefined && !isRuleSource(source)) return null
  if (level === undefined || copy.levels[level] === undefined) {
    return { tone: 'warning', text: copy.levels[0]! }
  }
  return {
    tone: level >= 2 ? 'success' : 'warning',
    text: `${copy.level(level)} · ${copy.levels[level]}`,
  }
}
