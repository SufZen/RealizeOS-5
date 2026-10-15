/**
 * Task 3 sends `notice` events (`tools_unavailable`, `tools_error`) in the
 * chat stream. The trail keeps them and "What I used" shows each as a short
 * warning line, in our words by code (English or Hebrew), else the server's
 * message.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { emptyTrail, normalizeTrail, toolRows, trailNotices, withEvent } from '@/lib/chat-stream'
import { llmSettingsText, noticeLine } from '@/lib/llm-settings-text'
import { TrailPanel } from './trail-panel'

const locale = vi.hoisted(() => ({ language: 'en' }))
vi.mock('@/components/locale-provider', () => ({
  useLocale: () => ({ language: locale.language, dir: locale.language === 'he' ? 'rtl' : 'ltr' }),
}))

afterEach(() => {
  locale.language = 'en'
})

function render(trail: ReturnType<typeof emptyTrail>): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <TrailPanel trail={trail} anchorPrefix="m1" />
    </MemoryRouter>,
  )
}

describe('notice events in the trail', () => {
  it('are kept as they arrive and never become tool rows', () => {
    let trail = emptyTrail()
    trail = withEvent(trail, { type: 'notice', code: 'tools_unavailable', message: 'no tools' })
    trail = withEvent(trail, { type: 'tool_call', id: 't1', name: 'sheets_read', input: {} })
    expect(trailNotices(trail.steps)).toEqual([
      { type: 'notice', code: 'tools_unavailable', message: 'no tools' },
    ])
    expect(toolRows(trail.steps).map((r) => r.name)).toEqual(['sheets_read'])
  })

  it('survive a stored trail', () => {
    const stored = normalizeTrail({
      sources: [],
      steps: [{ type: 'notice', code: 'tools_error', message: 'boom' }],
    })
    expect(trailNotices(stored!.steps)).toHaveLength(1)
  })
})

describe('notice words', () => {
  it('uses our words by code in each language', () => {
    expect(noticeLine({ code: 'tools_unavailable', message: 'server text' }, 'en')).toContain(
      'can’t use tools',
    )
    expect(noticeLine({ code: 'tools_unavailable', message: 'server text' }, 'he')).toMatch(/[א-ת]/)
    expect(noticeLine({ code: 'tools_error' }, 'he')).toMatch(/[א-ת]/)
  })

  it('falls back to the server message, then a generic line', () => {
    expect(noticeLine({ code: 'something_new', message: ' From the server ' }, 'en')).toBe(
      'From the server',
    )
    expect(noticeLine({}, 'en')).toBe('Something limited this answer.')
    expect(noticeLine({}, 'he')).toMatch(/[א-ת]/)
  })

  it('never takes a code from the object prototype', () => {
    for (const code of ['constructor', 'toString', '__proto__', 'hasOwnProperty']) {
      expect(noticeLine({ code, message: 'server said' }, 'en')).toBe('server said')
      expect(noticeLine({ code }, 'en')).toBe('Something limited this answer.')
    }
  })
})

describe('TrailPanel notices', () => {
  it('shows a warning line, even when the answer has no sources or tools', () => {
    const html = render({
      sources: [],
      steps: [{ type: 'notice', code: 'tools_unavailable', message: 'x' }],
    })
    expect(html).toContain('What I used')
    expect(html).toContain('role="status"')
    expect(html).toContain('can’t use tools here')
  })

  it('reads in Hebrew when the dashboard is Hebrew', () => {
    locale.language = 'he'
    const html = render({ sources: [], steps: [{ type: 'notice', code: 'tools_error' }] })
    expect(html).toContain(noticeLine({ code: 'tools_error' }, 'he'))
    expect(html).not.toContain('A tool call failed')
  })

  it('shows nothing for an empty trail', () => {
    expect(render(emptyTrail())).toBe('')
  })
})

describe('settings words', () => {
  it('Hebrew and English define the same keys', () => {
    const en = llmSettingsText('en')
    const he = llmSettingsText('he-IL')
    expect(Object.keys(he).sort()).toEqual(Object.keys(en).sort())
    expect(he.tierLabel.fast).not.toBe(en.tierLabel.fast)
    expect(he.saveError('x')).toContain('x')
    expect(en.saveError('x')).toContain('x')
  })
})
