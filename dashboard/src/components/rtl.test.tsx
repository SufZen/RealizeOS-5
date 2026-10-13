/**
 * RTL rendering (STORY-19): Hebrew content gets its own direction and the
 * layout uses logical (start/end) classes, so it mirrors under dir="rtl".
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import DocsPage from '@/pages/docs-page'
import { ApprovalCard } from './approval-card'
import { ChatMessage, type ChatMsg } from './chat-message'
import { ConnectStep, DoneStep, WelcomeStep, WizardSheet } from './onboarding-wizard'
import { DEFAULT_TOUR_STEPS, TourPopover } from './tour-provider'

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

  it('onboarding wizard: every step mirrors, and its arrows turn in RTL', () => {
    const noop = async () => {}
    const html = render(
      <>
        <WizardSheet step={0} footer={null}>
          <WelcomeStep />
        </WizardSheet>
        <WizardSheet step={1} footer={null}>
          <ConnectStep connected={new Set(['ollama'])} onSave={noop} />
        </WizardSheet>
        <WizardSheet step={2} footer={null}>
          <DoneStep providers={['Ollama (Local)']} animate={false} />
        </WizardSheet>
      </>,
    )
    expect(html).toContain('Welcome to RealizeOS')
    expect(html).toContain('Connect an AI provider')
    expect(html).toContain('You’re all set')
    expect(html).toContain('aria-valuenow="2"') // the sheet's progress line
    expect(html).toContain('dir="ltr"') // keys and URLs stay left-to-right inside RTL
    expect(html).toContain('end-[3px]') // show/hide sits at the inline end of the key field
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
  })

  it('tour popover: mirrors, and Back/Next point the reading direction', () => {
    const html = render(
      <TourPopover
        step={DEFAULT_TOUR_STEPS[2]!}
        stepIndex={2}
        totalSteps={DEFAULT_TOUR_STEPS.length}
        onNext={() => {}}
        onPrev={() => {}}
        onSkip={() => {}}
      />,
    )
    expect(html).toContain('Step 3 of 16')
    expect(html).toContain('aria-label="Close tour"')
    expect(html.match(/rtl:rotate-180/g)?.length).toBe(2)
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
  })

  it('docs page: logical sides only, and icons instead of emoji', () => {
    const html = render(<DocsPage />)
    expect(html).toContain('Welcome to RealizeOS V5')
    expect(html).not.toMatch(/\p{Extended_Pictographic}/u)
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
  })
})
