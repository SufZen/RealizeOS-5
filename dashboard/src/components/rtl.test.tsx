/**
 * RTL rendering (STORY-19): Hebrew content gets its own direction and the
 * layout uses logical (start/end) classes, so it mirrors under dir="rtl".
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import DocsPage from '@/pages/docs-page'
import { AgentDetailView } from '@/pages/agent-detail'
import { AgentTokensView } from '@/pages/agent-tokens-page'
import { EMPTY_FORM, INITIAL_TOKENS_STATE } from '@/lib/agent-tokens'
import { agentTokensText } from '@/lib/agent-tokens-text'
import { onboardingText } from '@/lib/onboarding-text'
import { agentControlsGate } from '@/lib/permissions'
import { ApprovalCard } from './approval-card'
import { ChatMessage, type ChatMsg } from './chat-message'
import {
  ConnectStep,
  DoneStep,
  WelcomeStep,
  WizardLanguageButton,
  WizardSheet,
} from './onboarding-wizard'
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

  it('chat trail: rule rows with their level mirror, and the pack id stays LTR', () => {
    const html = render(
      <ChatMessage
        msg={{
          role: 'assistant',
          id: 8,
          content: 'חשבון חלקי צמוד למדד תשומות הבנייה [R1].',
          trail: {
            sources: [
              {
                id: 'R1',
                title: 'חשבון חלקי צמוד למדד תשומות הבנייה',
                path: 'https://www.cbs.gov.il/',
                layer: 'market',
                pack: 'il@0.1.0',
                verification: 1,
                as_of: '2026-10-13',
              },
            ],
            steps: [],
          },
        }}
        anchorPrefix="trail-m-8"
      />,
    )
    expect(html).toContain('aria-label="Rule R1"')
    expect(html).toContain('Level 1 · draft — not reviewed')
    expect(html).toContain('<bdi dir="ltr" class="font-mono text-subtle-foreground">il@0.1.0</bdi>')
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

  it('onboarding wizard in Hebrew: every string translated, the sheet right-to-left', () => {
    const noop = async () => {}
    const he = onboardingText('he')
    const html = render(
      <>
        <WizardSheet step={0} footer={null} text={he}>
          <WelcomeStep text={he} />
        </WizardSheet>
        <WizardSheet step={1} footer={null} text={he}>
          <ConnectStep connected={new Set(['ollama'])} onSave={noop} onPrimary={noop} text={he} />
        </WizardSheet>
        <WizardSheet
          step={2}
          footer={null}
          text={he}
          headerEnd={<WizardLanguageButton text={he} onSwitch={() => {}} />}
        >
          <DoneStep providers={['Ollama (Local)']} animate={false} text={he} />
        </WizardSheet>
      </>,
    )
    // The sheet carries its language and direction itself.
    expect(html.match(/lang="he" dir="rtl"/g)?.length).toBe(3)
    expect(html).toContain('ברוכים הבאים ל-RealizeOS')
    expect(html).toContain('סולם אמון')
    expect(html).toContain('חיבור ספק AI')
    expect(html).toContain('מפתח API')
    expect(html).toContain('aria-label="הצגת המפתח"')
    expect(html).not.toContain('>מומלץ<') // no provider is recommended over another
    expect(html).toContain('ספק ראשי') // the primary-provider choice, once one is connected
    expect(html).toContain('>מחובר<')
    expect(html).toContain('הכול מוכן')
    expect(html).toContain('<span class="font-medium text-foreground">ספק אחד</span>')
    expect(html).toContain('Ollama (Local) חובר')
    expect(html).toContain('aria-valuetext="שלב 2 מתוך 3"')
    expect(html).toContain('<span>הגדרה</span><span>3 מתוך 3</span>')
    // The language button offers English, named in Hebrew.
    expect(html).toContain('aria-label="מעבר לאנגלית (English)"')
    expect(html).toContain('<span lang="en">English</span>')
    // Product names, keys and URLs stay as they are, left to right.
    expect(html).toContain('<bdi>Claude (Anthropic)</bdi>')
    expect(html).toContain('dir="ltr"')
    // No English left behind.
    for (const english of [
      'Welcome to RealizeOS',
      'Connect an AI provider',
      'You’re all set',
      'Recommended',
      'Primary provider',
      'API key',
      'What to do next',
      'Setup progress',
    ]) {
      expect(html).not.toContain(english)
    }
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
  })

  it('onboarding wizard in English stays left-to-right and offers Hebrew', () => {
    const en = onboardingText('en')
    const html = render(
      <WizardSheet
        step={0}
        footer={null}
        text={en}
        headerEnd={<WizardLanguageButton text={en} onSwitch={() => {}} />}
      >
        <WelcomeStep text={en} />
      </WizardSheet>,
    )
    expect(html).toContain('lang="en" dir="ltr"')
    expect(html).toContain('aria-label="Switch to Hebrew (עברית)"')
    expect(html).toContain('<span lang="he">עברית</span>')
    expect(html).toContain('ms-auto') // the language button sits at the inline end
  })

  it('agent tokens page: Hebrew, logical sides, and the token stays left-to-right', () => {
    const html = render(
      <AgentTokensView
        text={agentTokensText('he')}
        language="he"
        tokens={[
          {
            id: '3f9a0c1d2e4b',
            name: 'claude-acme',
            principal: 'agent:3f9a0c1d2e4b',
            user: 'dana@acme.io',
            ventures: ['tower-b'],
            status: 'active',
            created_by: 'owner@realization.co.il',
            created_at: '2026-10-13T09:00:00+00:00',
            expires_at: null,
            last_used_at: null,
            revoked_at: null,
            revoked_by: null,
          },
        ]}
        enabled={false}
        loading={false}
        error={null}
        ventures={[{ key: 'tower-b', name: 'מגדל B' }]}
        form={{ ...EMPTY_FORM, ventures: ['tower-b'] }}
        onFormChange={() => {}}
        problems={['name']}
        createError={null}
        creating={false}
        onCreate={() => {}}
        state={{
          ...INITIAL_TOKENS_STATE,
          created: {
            token: 'rzag_3f9a0c1d2e4b_Zx9-secret-part-that-is-long-enough-123456',
            agent_token: {
              id: '3f9a0c1d2e4b',
              name: 'claude-acme',
              principal: 'agent:3f9a0c1d2e4b',
              user: 'dana@acme.io',
              ventures: ['tower-b'],
              status: 'active',
              created_by: 'owner@realization.co.il',
              created_at: '2026-10-13T09:00:00+00:00',
              expires_at: null,
              last_used_at: null,
              revoked_at: null,
              revoked_by: null,
            },
          },
        }}
        onCopy={() => {}}
        onDismissCreated={() => {}}
        onAskRevoke={() => {}}
        onCancelRevoke={() => {}}
        onConfirmRevoke={() => {}}
        revokeBusy={false}
        onRefresh={() => {}}
      />,
    )
    expect(html).toContain('טוקנים לסוכנים')
    expect(html).toContain('הטוקנים לסוכנים כבויים')
    expect(html).toContain('<bdi>מגדל B</bdi>')
    expect(html).toContain('בלי תפוגה')
    expect(html).toContain('עד 64 אותיות באנגלית')
    expect(html).toMatch(/<input[^>]*dir="ltr"[^>]*value="rzag_/)
    expect(html).toContain('<code dir="ltr" class="font-mono">')
    expect(html).toContain('rtl:rotate-180') // the breadcrumb chevron turns
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
  })

  it('approval card from an outside agent: the badge mirrors, the name stays isolated', () => {
    const html = render(
      <ApprovalCard
        language="he"
        approval={{
          id: 'apv-9',
          venture_key: 'tower-b',
          agent_key: 'claude-acme',
          action_type: 'mcp_write',
          action_name: 'mcp:run_workflow',
          status: 'pending',
          created_at: '2026-10-13T09:00:00Z',
          params_json: JSON.stringify({ system_key: 'tower-b', workflow: 'דוח שבועי' }),
          requested_by: 'agent:3f9a0c1d2e4b',
          requested_by_agent: { token_id: '3f9a0c1d2e4b', name: 'claude-acme' },
        }}
      />,
    )
    expect(html).toContain('סוכן חיצוני: <bdi>claude-acme</bdi>')
    expect(html).toContain('aria-label="הרצת תהליך עבודה: ממתין"')
    expect(html).toContain('סוכן חיצוני ביקש את זה דרך MCP')
    expect(html).toContain('דוח שבועי')
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
  })

  it('agent detail: the view-only line and the back arrow mirror', () => {
    const html = render(
      <AgentDetailView
        data={{
          key: 'site-payments',
          venture_key: 'tower-b',
          definition_path: 'systems/tower-b/A-agents/site-payments.md',
          definition: '# תשלומים באתר',
          status: 'idle',
          last_run_at: null,
          last_error: null,
          schedule_cron: null,
          schedule_interval_sec: null,
          next_run_at: null,
          recent_activity: [],
        }}
        ventureKey="tower-b"
        gate={agentControlsGate({ role: 'viewer' })}
        onPause={() => {}}
        onResume={() => {}}
        onScheduleSaved={() => {}}
      />,
    )
    expect(html).toContain('data-gate="agent"')
    expect(html).toContain('rtl:rotate-180')
    expect(html).toContain('<pre dir="auto"')
    expect(html).toContain('<bdi>tower-b</bdi>')
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
