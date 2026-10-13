/**
 * The trust matrix with packs (spec 010 §3.1): each venture shows where a pack
 * or the firm tightened an action, and the defaults that were ignored because
 * they would loosen trust. English and Hebrew; mirror-safe in RTL.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { decisionText, decisionTone, ignoredDefaults, type VentureTrust } from '@/lib/trust-copy'
import { VentureTrustPanel } from './venture-trust'

const ACME: VentureTrust = {
  name: 'Acme Tower',
  layers: [
    { layer: 'firm', pack: null },
    { layer: 'market', pack: 'pt@0.1.0' },
    { layer: 'profession', pack: 'developer@0.1.0' },
  ],
  actions: [
    {
      action: 'data_write',
      governed_by: null,
      ladder: 'approve',
      effective: 'block',
      tightened: true,
      source: {
        layer: 'market',
        pack: 'pt@0.1.0',
        key: 'data_write',
        value: 'block',
        label: 'market pack pt@0.1.0',
      },
      ignored: [],
    },
    {
      action: 'send_email',
      governed_by: null,
      ladder: 'approve',
      effective: 'approve',
      tightened: false,
      source: null,
      ignored: [
        {
          layer: 'profession',
          pack: 'developer@0.1.0',
          key: 'send_email',
          value: 'auto',
          label: 'profession pack developer@0.1.0',
          reason: 'loosen',
        },
      ],
    },
    {
      action: 'gmail_send',
      governed_by: 'send_email',
      ladder: 'approve',
      effective: 'approve',
      tightened: false,
      source: null,
      ignored: [
        {
          layer: 'profession',
          pack: 'developer@0.1.0',
          key: 'send_email',
          value: 'auto',
          label: 'profession pack developer@0.1.0',
          reason: 'loosen',
        },
      ],
    },
    {
      action: 'ledger_append',
      governed_by: 'unknown_write',
      ladder: 'auto',
      effective: 'approve',
      tightened: true,
      source: {
        layer: 'firm',
        pack: null,
        key: 'ledger_append',
        value: 'approve',
        label: 'firm overrides',
      },
      ignored: [],
    },
  ],
  warnings: [
    'profession pack developer@0.1.0 would loosen send_email from approve to auto; ignored (packs only tighten trust)',
  ],
}

const PLAIN: VentureTrust = {
  name: 'Plain',
  layers: [{ layer: 'firm', pack: null }],
  actions: [
    {
      action: 'send_email',
      governed_by: null,
      ladder: 'approve',
      effective: 'approve',
      tightened: false,
      source: null,
      ignored: [],
    },
  ],
  warnings: [],
}

/** Tailwind classes tied to a physical side, which would not flip in RTL. */
const PHYSICAL_CLASS =
  /(?:^|\s)-?(?:ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r)-|(?:^|\s)text-(?:left|right)(?:\s|$)/

function rows(html: string): string[] {
  return [...html.matchAll(/<tr[^>]*>(.*?)<\/tr>/g)].map((m) => m[1]!.replace(/<[^>]+>/g, ' '))
}

describe('VentureTrustPanel', () => {
  it('shows each tightened action with the ladder, what applies, and the pack that tightened it', () => {
    const html = renderToStaticMarkup(<VentureTrustPanel venture={ACME} language="en" />)

    expect(html).toContain('Packs and firm rules · Acme Tower')
    const body = rows(html).slice(1)
    expect(body).toHaveLength(2) // only tightened rows by default
    expect(body[0]).toMatch(/data_write .* Needs approval .* Blocked .* market pack .* pt@0\.1\.0/)
    expect(body[1]).toMatch(/ledger_append .*falls under .*unknown_write/)
    expect(body[1]).toContain('firm overrides')
    expect(html).toContain('data-decision="block"')
    expect(html).toContain('Show every action')
  })

  it('lists every ignored loosening once, as a warning', () => {
    const html = renderToStaticMarkup(<VentureTrustPanel venture={ACME} language="en" />)

    expect(html).toContain('Ignored defaults')
    const items = [...html.matchAll(/<li>(.*?)<\/li>/g)].map((m) => m[1]!.replace(/<[^>]+>/g, ''))
    expect(items).toEqual([
      'profession pack developer@0.1.0: send_email = auto would loosen the trust ladder. Ignored: packs only tighten trust.',
    ])
    expect(ignoredDefaults(ACME.actions)).toHaveLength(1)
  })

  it('can show every action, untouched ones from the trust ladder', () => {
    const html = renderToStaticMarkup(<VentureTrustPanel venture={ACME} language="en" showAll />)
    expect(rows(html).slice(1)).toHaveLength(4)
    expect(html).toContain('Show tightened only')
    expect(html).toContain('trust ladder')
  })

  it('says when nothing is tightened', () => {
    const html = renderToStaticMarkup(<VentureTrustPanel venture={PLAIN} language="en" />)
    expect(html).toContain('No pack or firm default tightens this venture’s trust at this level.')
    expect(html).not.toContain('<table')
    expect(html).not.toContain('Ignored defaults')
  })

  it('speaks Hebrew, keeps codes and pack ids isolated, and uses logical sides only', () => {
    const html = renderToStaticMarkup(<VentureTrustPanel venture={ACME} language="he" showAll />)

    expect(html).toContain('חבילות וכללי המשרד · Acme Tower')
    expect(html).toContain('סולם האמון')
    expect(html).toContain('הוחמר על ידי')
    expect(html).toContain('חסום')
    expect(html).toContain('דורש אישור')
    expect(html).toContain('חבילת שוק')
    expect(html).toContain('הגדרות המשרד')
    expect(html).toContain('הגדרות שנדחו')
    expect(html).toContain('<bdi dir="ltr" class="font-mono text-xs">pt@0.1.0</bdi>')
    expect(html).toContain('<bdi dir="ltr" class="font-mono text-xs">data_write</bdi>')
    for (const cls of [...html.matchAll(/class="([^"]*)"/g)].map((m) => m[1]!)) {
      expect(cls).not.toMatch(PHYSICAL_CLASS)
    }
  })

  it('names decisions in words with a tone that means something', () => {
    expect(decisionText('block', 'en')).toBe('Blocked')
    expect(decisionText('approve', 'he')).toBe('דורש אישור')
    expect(decisionText('sometimes', 'en')).toBe('sometimes')
    expect([decisionTone('block'), decisionTone('approve'), decisionTone('auto')]).toEqual([
      'danger',
      'accent',
      'neutral',
    ])
  })
})
