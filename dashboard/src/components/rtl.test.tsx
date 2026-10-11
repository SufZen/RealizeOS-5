/**
 * RTL rendering (STORY-19): Hebrew content gets its own direction and the
 * layout uses logical (start/end) classes, so it mirrors under dir="rtl".
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ApprovalCard } from './approval-card'
import { ChatMessage, type ChatMsg } from './chat-message'

/** Tailwind classes tied to a physical side, which would not flip in RTL. */
const PHYSICAL_CLASS =
  /(?:^|\s)-?(?:ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r)-|(?:^|\s)text-(?:left|right)(?:\s|$)/

function classesOf(html: string): string[] {
  return [...html.matchAll(/class="([^"]*)"/g)].map((m) => m[1]!)
}

const HEBREW_ANSWER: ChatMsg = {
  role: 'assistant',
  content: 'נשארו 900 אלף אירו בתקציב של מגדל B [S1], לפי גיליון התשלומים.',
  agent_key: 'finance',
  id: 7,
  trail: {
    sources: [{ id: 'S1', title: 'תקציב מגדל B', path: 'systems/tower-b/B-brain/budget.md' }],
    steps: [
      { type: 'tool_call', id: 't1', name: 'sheets_read', input: {} },
      {
        type: 'tool_result',
        id: 't1',
        name: 'sheets_read',
        success: true,
        held: false,
        duration_ms: 412,
      },
      { type: 'approval_requested', id: 't2', name: 'sheets_append', request_id: 'apv-1' },
    ],
  },
}

const HEBREW_USER: ChatMsg = { role: 'user', content: 'כמה נשאר בתקציב של מגדל B?' }

function render(node: React.ReactNode): string {
  return renderToStaticMarkup(<MemoryRouter>{node}</MemoryRouter>)
}

describe('RTL rendering', () => {
  it('chat messages: content and trail follow their own direction', () => {
    const html = render(
      <>
        <ChatMessage msg={HEBREW_USER} anchorPrefix="trail-u" />
        <ChatMessage msg={HEBREW_ANSWER} anchorPrefix="trail-m-7" />
      </>,
    )
    expect(html).toContain('dir="auto"')
    expect(html).toContain('ms-auto') // the user's bubble sits at the inline end in LTR and RTL
    expect(html).toContain('aria-label="Source S1"')
    expect(html).toContain('id="trail-m-7-S1"')
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
    expect(html).toMatchSnapshot()
  })

  it('approval cards: Hebrew parameters keep their direction', () => {
    const html = render(
      <ApprovalCard
        approval={{
          id: 'apv-1',
          venture_key: 'tower-b',
          agent_key: 'site-payments',
          action_type: 'sheets_append',
          action_name: 'sheets_append',
          status: 'pending',
          created_at: '2026-10-11T09:00:00',
          params_json: JSON.stringify({ שורה: 'תשלום 7 לקבלן — שלב שלד', סכום: '120,000 €' }),
        }}
      />,
    )
    expect(html).toContain('dir="auto"')
    expect(html).toContain('תשלום 7 לקבלן')
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
    expect(html).toMatchSnapshot()
  })
})
