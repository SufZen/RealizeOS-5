/**
 * Review findings on the approvals surface:
 * - D1: a decision-log result that isn't a decision (inputs, rejected
 *   proposals) says nothing; a queued retry says it will be added, not that
 *   it failed.
 * - D6: a pack verification can only be decided by an owner with every
 *   venture, so nobody else gets buttons the server would refuse.
 * - D7: server text (errors, output, who decided) is isolated with <bdi>.
 * - D10: times on a card follow the person's language.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { ApprovalCard, type Approval } from '@/components/approval-card'
import { approvalText } from '@/lib/approval-text'
import { canDecide, canDecideOwnerOnly } from '@/lib/permissions'
import { formatDateTime } from '@/lib/locale'
import {
  ApprovalsView,
  OutcomeBanner,
  type ApprovalsViewProps,
  type DecisionResponse,
} from './approvals-page'

const NOW = Date.parse('2026-10-13T12:00:00Z')
const noop = () => {}

const HELD: Approval = {
  id: 'apv-1',
  venture_key: 'acme',
  agent_key: 'writer',
  action_type: 'send_email',
  action_name: 'send_email',
  status: 'pending',
  created_at: '2026-10-13T09:00:00Z',
  expires_at: '2026-10-13T13:00:00.000000Z',
}

const PACK: Approval = {
  ...HELD,
  id: 'apv-pack',
  action_type: 'pack_verify',
  action_name: null,
}

function banner(outcome: DecisionResponse, language = 'en'): string {
  return renderToStaticMarkup(
    <OutcomeBanner outcome={outcome} now={NOW} text={approvalText(language)} onClose={noop} />,
  )
}

function view(overrides: Partial<ApprovalsViewProps> = {}): string {
  const props: ApprovalsViewProps = {
    text: approvalText('en'),
    language: 'en',
    tab: 'pending',
    onTabChange: noop,
    onRefresh: noop,
    approvals: [HELD, PACK],
    loading: false,
    error: null,
    now: NOW,
    blockedReason: null,
    busyId: null,
    problems: {},
    outcome: null,
    onDismissOutcome: noop,
    onDismissProblem: noop,
    onDecide: noop,
    notes: {},
    onNoteChange: noop,
    ...overrides,
  }
  return renderToStaticMarkup(
    <MemoryRouter>
      <ApprovalsView {...props} />
    </MemoryRouter>,
  )
}

/** The markup of each card, in list order. */
function cards(html: string): string[] {
  return html.split('<article').slice(1)
}

describe('D1: decision-log line', () => {
  const answered: DecisionResponse = {
    ...HELD,
    action_type: 'skill_input',
    action_name: null,
    status: 'answered',
  }

  it('an answer (not a decision) shows no decision-log line at all', () => {
    const html = banner({
      ...answered,
      decision_log: { logged: false, pending: false, error: null },
    })
    expect(html).not.toContain('data-decision-log')
    expect(html).not.toContain('decision log')
  })

  it('a rejected proposal (not a decision) shows none either, in Hebrew too', () => {
    const rejected: DecisionResponse = { ...HELD, status: 'rejected' }
    const log = { logged: false, pending: false, error: null, decision_id: null }
    expect(banner({ ...rejected, decision_log: log })).not.toContain('data-decision-log')
    expect(banner({ ...rejected, decision_log: log }, 'he')).not.toContain('יומן ההחלטות')
  })

  it('a queued retry says it will be added, not that it failed', () => {
    const html = banner({
      ...HELD,
      status: 'approved',
      action_name: null,
      decision_log: { logged: false, pending: true, error: 'disk full', decision_id: null },
    })
    expect(html).toContain('data-decision-log="queued"')
    expect(html).toContain('Queued for the decision log; it will be added shortly.')
    expect(html).not.toContain('Not added')
    expect(html).not.toContain('text-amber-400"><svg')
  })

  it('a real failure still says so, with the error isolated', () => {
    const html = banner(
      {
        ...HELD,
        status: 'approved',
        action_name: null,
        decision_log: { logged: false, pending: false, error: 'read-only KB' },
      },
      'he',
    )
    expect(html).toContain('data-decision-log="missing"')
    expect(html).toContain('לא נוסף ליומן ההחלטות: <bdi>read-only KB</bdi>')
  })

  it('on a card in history: nothing for an answer, the queued line for a retry', () => {
    const quiet = renderToStaticMarkup(
      <ApprovalCard
        approval={{ ...answered, decision_log: { logged: false, pending: false, error: null } }}
        now={NOW}
      />,
    )
    expect(quiet).not.toContain('data-decision-log')
    // Nothing else to show: no empty body under the header.
    expect(quiet).not.toContain('grid gap-3 px-4 pb-4')

    const queued = renderToStaticMarkup(
      <ApprovalCard
        approval={{
          ...HELD,
          status: 'approved',
          action_name: null,
          decision_log: { logged: false, pending: true, error: 'locked' },
        }}
        now={NOW}
        language="he"
      />,
    )
    expect(queued).toContain('ממתין בתור ליומן ההחלטות; יתווסף בקרוב.')
  })
})

describe('D6: pack verification is an owner’s decision', () => {
  it('only an owner with every venture may decide it', () => {
    const owner = { role: 'owner', ventures: null }
    expect(canDecide(owner, 'pack_verify')).toBe(true)
    expect(canDecideOwnerOnly(owner)).toBe(true)
    for (const actor of [
      { role: 'admin', ventures: null },
      { role: 'operator', ventures: null },
      { role: 'owner', ventures: ['acme'] },
      { role: 'approver', ventures: null, permissions: ['pipeline:approve'] },
    ]) {
      expect(canDecide(actor, 'pack_verify')).toBe(false)
      expect(canDecideOwnerOnly(actor)).toBe(false)
      // Everything else stays theirs to decide.
      expect(canDecide(actor, 'send_email')).toBe(true)
    }
    expect(canDecide({ role: 'viewer', ventures: null }, 'pack_verify')).toBe(false)
  })

  it('an operator gets the buttons on other items, and a reason on the pack item', () => {
    const text = approvalText('en')
    const [email, pack] = cards(view({ ownerOnlyReason: text.ownerOnly }))
    expect(email).toContain('Approve &amp; run')
    expect(email).toContain('Note for this decision')
    expect(pack).not.toContain('>Approve<')
    expect(pack).not.toContain('>Reject<')
    expect(pack).not.toContain('Note for this decision')
    expect(pack).toContain('data-gate="decide"')
    expect(pack).toContain('only an owner with access to every venture can approve or reject it')
  })

  it('an owner gets the buttons on the pack item', () => {
    const [, pack] = cards(view({ ownerOnlyReason: null }))
    expect(pack).toContain('>Approve<')
    expect(pack).toContain('>Reject<')
  })

  it('a viewer gets the view-only reason everywhere, whatever the item', () => {
    const text = approvalText('he')
    const html = view({
      text,
      language: 'he',
      blockedReason: text.viewOnly('viewer'),
      ownerOnlyReason: text.ownerOnly,
    })
    for (const card of cards(html)) {
      expect(card).toContain('צפייה בלבד')
      expect(card).not.toContain('רק בעלים')
    }
  })

  it('Hebrew reason', () => {
    const text = approvalText('he')
    const [, pack] = cards(view({ text, language: 'he', ownerOnlyReason: text.ownerOnly }))
    expect(pack).toContain('רק בעלים עם גישה לכל המיזמים')
  })
})

describe('D7: server text is isolated', () => {
  it('who decided first, in the 409 sentence', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={{ ...HELD, status: 'approved' }}
        now={NOW}
        language="he"
        problem={{
          kind: 'already_decided',
          final: true,
          approval: { status: 'approved', decided_by: 'owner@test.local' },
        }}
      />,
    )
    expect(html).toContain('(אושר ע״י <bdi>owner@test.local</bdi>)')
  })

  it('a refusal and a server error', () => {
    const forbidden = renderToStaticMarkup(
      <ApprovalCard
        approval={HELD}
        now={NOW}
        problem={{ kind: 'forbidden', final: false, detail: 'needs pipeline:approve' }}
      />,
    )
    expect(forbidden).toContain('You can’t decide this request: <bdi>needs pipeline:approve</bdi>')
  })

  it('a skill’s answer shown as the banner message', () => {
    const html = banner(
      {
        ...HELD,
        action_type: 'skill_input',
        action_name: null,
        status: 'answered',
        skill_output: 'Sent to ACME Ltd.',
      },
      'he',
    )
    expect(html).toContain('<bdi>Sent to ACME Ltd.</bdi>')
  })

  it('a stored output and error in history, in Hebrew', () => {
    const failed = renderToStaticMarkup(
      <ApprovalCard
        approval={{
          ...HELD,
          status: 'approved',
          execution_status: 'failed',
          executed_at: '2026-10-13T12:01:00Z',
          error: '403 insufficient scopes',
        }}
        now={NOW}
        language="he"
      />,
    )
    expect(failed).toContain('אושר, אבל הביצוע נכשל: <bdi>403 insufficient scopes</bdi>.')
    // The agent and venture keys are isolated too.
    expect(failed).toContain('סוכן: <bdi>writer</bdi>')
    expect(failed).toContain('מיזם: <bdi>acme</bdi>')
  })
})

describe('D10: times follow the language', () => {
  it('formatDateTime uses Hebrew or English', () => {
    const iso = '2026-10-13T13:00:00Z'
    const he = formatDateTime(iso, 'he')
    const en = formatDateTime(iso, 'en')
    expect(he).not.toBe(en)
    expect(he).toMatch(/[֐-׿]/) // Hebrew month name
    expect(en).toMatch(/Oct/)
    expect(formatDateTime('not a date', 'he')).toBe('not a date')
  })

  it('an expired card shows its time in the card’s language', () => {
    const later = Date.parse('2026-10-13T13:00:01Z')
    const html = renderToStaticMarkup(<ApprovalCard approval={HELD} now={later} language="he" />)
    expect(html).toContain(`<bdi>${formatDateTime(HELD.expires_at!, 'he')}</bdi>`)
  })
})
