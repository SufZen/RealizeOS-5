/**
 * Design system v2 guards: colour contrast for every text token in both
 * modes, mirror-safe markup for the new primitives, and reduced motion.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Button, IconButton } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { Panel } from '@/components/ui/panel'
import { Stamp } from '@/components/ui/stamp'
import { Tabs, Segmented } from '@/components/ui/tabs'
import { TitleBlock } from '@/components/ui/title-block'
import { Trail, SourceRef } from '@/components/ui/trail'

const dir = resolve(__dirname)
const tokensCss = readFileSync(resolve(dir, 'tokens.css'), 'utf-8')
const motionCss = readFileSync(resolve(dir, 'motion.css'), 'utf-8')

function block(selector: string): Record<string, string> {
  const start = tokensCss.indexOf(selector)
  const open = tokensCss.indexOf('{', start)
  const close = tokensCss.indexOf('\n}', open)
  const body = tokensCss.slice(open, close)
  return Object.fromEntries(
    [...body.matchAll(/(--rz-[a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1]!, m[2]!]),
  )
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi! + 0.05) / (lo! + 0.05)
}

const MODES = {
  dark: block(":root,\n[data-mode='dark']"),
  light: block("[data-mode='light'] {"),
}

/** [foreground, background, minimum ratio]. 4.5 = WCAG AA body text; 3 = placeholder. */
const PAIRS: [string, string, number][] = [
  ['fg', 'bg', 4.5],
  ['fg', 'bg-raised', 4.5],
  ['fg-muted', 'bg', 4.5],
  ['fg-muted', 'bg-raised', 4.5],
  ['fg-subtle', 'bg', 4.5],
  ['fg-subtle', 'bg-raised', 4.5],
  ['fg-faint', 'bg-raised', 3],
  ['accent-text', 'bg', 4.5],
  ['accent-text', 'bg-raised', 4.5],
  ['accent-fg', 'accent', 4.5],
  ['success', 'bg-raised', 4.5],
  ['warning', 'bg-raised', 4.5],
  ['danger', 'bg-raised', 4.5],
  ['info', 'bg-raised', 4.5],
  ['agent', 'bg-raised', 4.5],
]

describe('colour tokens', () => {
  for (const [mode, tokens] of Object.entries(MODES)) {
    it.each(PAIRS)(`${mode}: --rz-%s on --rz-%s meets %s:1`, (fg, bg, min) => {
      const a = tokens[`--rz-${fg}`]
      const b = tokens[`--rz-${bg}`]
      expect(a, `--rz-${fg} defined in ${mode}`).toBeDefined()
      expect(b, `--rz-${bg} defined in ${mode}`).toBeDefined()
      expect(contrast(a!, b!)).toBeGreaterThanOrEqual(min)
    })
  }

  it('defines the same names in both modes', () => {
    expect(Object.keys(MODES.light).sort()).toEqual(Object.keys(MODES.dark).sort())
  })
})

/** Tailwind classes tied to a physical side, which would not flip in RTL (same rule as rtl.test). */
const PHYSICAL_CLASS =
  /(?:^|\s)-?(?:ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r)-|(?:^|\s)text-(?:left|right)(?:\s|$)/

describe('primitives are mirror-safe', () => {
  const html = renderToStaticMarkup(
    <MemoryRouter>
      <div dir="rtl">
        <TitleBlock
          title="אישורים"
          crumbs={[{ label: 'מיזמים', to: '/ventures' }, { label: 'אישורים' }]}
          reference={['מגדלי רמת אביב', 'Rev 14']}
          actions={<Button variant="primary">בדיקה</Button>}
        />
        <Panel title="חשבון 14" held actions={<Badge tone="accent">ממתין</Badge>}>
          <Trail
            steps={[
              {
                id: 'a',
                state: 'done',
                title: (
                  <>
                    קראתי את החשבון
                    <SourceRef n={1} title="PR-14.pdf" />
                  </>
                ),
              },
              { id: 'b', state: 'held', title: 'ממתין לך' },
            ]}
          />
          <Stamp decision="approved" by="דנה · 14:02" />
          <StatusDot state="agent" live label="רץ" />
          <IconButton label="עוד">…</IconButton>
        </Panel>
        <Tabs label="תצוגה" value="a" onChange={() => {}} items={[{ value: 'a', label: 'הכל' }]} />
        <Segmented
          label="מצב"
          value="a"
          onChange={() => {}}
          items={[{ value: 'a', label: 'רשימה' }]}
        />
        <EmptyState title="אין כאן כלום" />
      </div>
    </MemoryRouter>,
  )

  it('uses only logical side classes', () => {
    const classes = [...html.matchAll(/class="([^"]*)"/g)].map((m) => m[1]!)
    expect(classes.filter((c) => PHYSICAL_CLASS.test(c))).toEqual([])
  })

  it('names every control', () => {
    expect(html).toContain('aria-label="עוד"')
    expect(html).toContain('aria-label="Source 1: PR-14.pdf"')
    expect(html).toContain('role="tablist"')
  })
})

describe('motion', () => {
  it('drops movement for people who ask for reduced motion', () => {
    expect(motionCss).toContain('@media (prefers-reduced-motion: reduce)')
    expect(motionCss).toMatch(/::view-transition-new\(\*\)/)
  })

  it('ships springs as CSS linear() with a cubic-bezier fallback', () => {
    expect(motionCss).toMatch(/--rz-spring-bounce:\s*cubic-bezier/)
    expect(motionCss).toMatch(/@supports \(transition-timing-function: linear\(0, 1\)\)/)
  })
})
