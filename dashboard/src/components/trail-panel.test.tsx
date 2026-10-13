/**
 * Rule-card provenance in the "What I used" trail (Codex audit N03): every
 * rule row shows its verification level in words, its layer and pack, and
 * its as-of date, whatever the answer says. KB sources stay as they were.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { normalizeTrail, type Trail, type TrailSource } from '@/lib/chat-stream'
import { levelLabel } from '@/lib/trail-copy'
import { ChatMessage } from './chat-message'
import { TrailPanel } from './trail-panel'

const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/components/locale-provider', () => ({
  useLocale: () => ({ language: locale.language, dir: locale.language === 'he' ? 'rtl' : 'ltr' }),
}))

afterEach(() => {
  locale.language = 'en'
})

const KB: TrailSource = { id: 'S1', title: 'Budget', path: 'systems/acme/B-brain/budget.md' }
const RULE: TrailSource = {
  id: 'R1',
  title: 'Public works contracts include price revision.',
  path: 'https://example.org/pt.price-revision',
  layer: 'market',
  pack: 'pt@0.1.0',
  verification: 1,
  as_of: '2026-10-13',
  review_by: '2099-04-13',
}

function render(node: React.ReactNode): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>)
}

function badges(html: string): string[] {
  return [...html.matchAll(/<span class="rz-badge[^"]*"[^>]*>([^<]*)<\/span>/g)].map((m) => m[1]!)
}

describe('level labels', () => {
  it('names every level on the ladder, level 1 always as a draft', () => {
    const at = (verification: number) => levelLabel({ ...RULE, verification }, 'en')
    expect([0, 1, 2, 3, 4].map((n) => at(n)?.text)).toEqual([
      'Level 0 · unverified',
      'Level 1 · draft — not reviewed',
      'Level 2 · reviewed',
      'Level 3 · maintained',
      'Level 4 · field-proven',
    ])
    expect([0, 1, 2, 3, 4].map((n) => at(n)?.tone)).toEqual([
      'warning',
      'warning',
      'success',
      'success',
      'success',
    ])
  })

  it('has Hebrew words for every level', () => {
    const he = [0, 1, 2, 3, 4].map((n) => levelLabel({ ...RULE, verification: n }, 'he')?.text)
    expect(he[1]).toBe('רמה 1 · טיוטה — לא נבדקה')
    expect(new Set(he).size).toBe(5)
  })

  it('a rule without a recorded level reads unverified; a KB source gets none', () => {
    const unlevelled: TrailSource = { ...RULE, verification: undefined }
    expect(levelLabel(unlevelled, 'en')).toEqual({ tone: 'warning', text: 'unverified' })
    expect(levelLabel({ ...RULE, verification: 9 }, 'en')).toEqual({
      tone: 'warning',
      text: 'unverified',
    })
    expect(levelLabel(KB, 'en')).toBeNull()
  })
})

describe('TrailPanel provenance', () => {
  it('shows the level, layer, pack and date on rule rows and nothing extra on KB rows', () => {
    const html = render(<TrailPanel trail={{ sources: [KB, RULE], steps: [] }} anchorPrefix="t" />)

    expect(badges(html)).toEqual(['Level 1 · draft — not reviewed'])
    expect(html).toContain('rz-badge--warning')
    expect(html).toContain('data-level="1"')
    expect(html).toContain('market')
    expect(html).toContain('pt@0.1.0')
    expect(html).toContain('as of 2026-10-13')
    expect(html).toContain('title="review by 2099-04-13"')
    expect(html).toContain('href="https://example.org/pt.price-revision"')
    expect(html).toContain('rel="noopener noreferrer"')
    expect(html).toContain('id="t-R1"')
    expect(html).toContain('id="t-S1"')
  })

  it('labels a firm rule without a pack, and never links a non-web source', () => {
    const firm: TrailSource = {
      id: 'R2',
      title: 'Our retention is 5%.',
      path: 'javascript:alert(1)',
      layer: 'firm',
      verification: 3,
    }
    const html = render(<TrailPanel trail={{ sources: [firm], steps: [] }} anchorPrefix="t" />)
    expect(badges(html)).toEqual(['Level 3 · maintained'])
    expect(html).toContain('rz-badge--success')
    expect(html).toContain('firm')
    expect(html).not.toContain('href=')
  })

  it('speaks Hebrew when the venture does', () => {
    locale.language = 'he'
    const trail: Trail = {
      sources: [RULE],
      steps: [{ type: 'approval_requested', id: 't1', name: 'sheets_append', request_id: 'a1' }],
    }
    const html = render(<TrailPanel trail={trail} anchorPrefix="t" />)
    expect(html).toContain('במה השתמשתי')
    expect(badges(html)).toEqual(['רמה 1 · טיוטה — לא נבדקה'])
    expect(html).toContain('שוק')
    expect(html).toContain('נכון ל־2026-10-13')
    expect(html).toContain('ממתין לאישור')
  })
})

describe('restored conversations', () => {
  it('a reloaded answer still shows each rule’s level and links its markers', () => {
    // What GET /api/conversations returns for one stored answer.
    const stored = {
      sources: [KB, RULE, { id: 'R2', title: 'Saved before levels', path: 'https://example.test' }],
      steps: [],
    }
    const html = render(
      <ChatMessage
        msg={{
          role: 'assistant',
          id: 7,
          content: 'Price revision applies [R1] and [R2]; 900k left [S1]. [R9] is unknown.',
          trail: normalizeTrail(stored),
        }}
        anchorPrefix="trail-m-7"
      />,
    )
    expect(badges(html)).toEqual(['Level 1 · draft — not reviewed', 'unverified'])
    expect(html).toContain('aria-label="Rule R1"')
    expect(html).toContain('aria-label="Rule R2"')
    expect(html).toContain('aria-label="Source S1"')
    for (const marker of ['R1', 'R2', 'S1']) expect(html).toContain(`id="trail-m-7-${marker}"`)
    expect(html).toContain('[R9]') // a marker with no trail row stays text
    expect(html).not.toContain('aria-label="Rule R9"')
  })
})
