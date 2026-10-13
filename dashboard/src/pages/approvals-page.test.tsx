/**
 * Codex audit N11, N04 (UI) and recommendation 7 on the approvals page: role
 * gating, inline problems, and an outcome banner that never calls a failed
 * or unknown execution a success.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import type { Approval } from '@/components/approval-card'
import { approvalText } from '@/lib/approval-text'
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

function view(overrides: Partial<ApprovalsViewProps> = {}): string {
  const text = approvalText('en')
  const props: ApprovalsViewProps = {
    text,
    language: 'en',
    tab: 'pending',
    onTabChange: noop,
    onRefresh: noop,
    approvals: [HELD],
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

describe('ApprovalsView', () => {
  it('a person who may decide gets the note and the decision buttons', () => {
    const html = view()
    expect(html).toContain('Approve &amp; run')
    expect(html).toContain('>Reject<')
    expect(html).toContain('aria-label="Note for this decision"')
    expect(html).toContain('Held for you')
    expect(html).toContain('Expired') // its own tab
  })

  it('a viewer sees no decision controls, and is told why', () => {
    const text = approvalText('en')
    const html = view({ blockedReason: text.viewOnly('viewer') })
    expect(html).not.toContain('Approve &amp; run')
    expect(html).not.toContain('>Reject<')
    expect(html).not.toContain('Note for this decision')
    expect(html).toContain('View only: your role (viewer)')
  })

  it('a decision error is shown on its card', () => {
    const html = view({ problems: { 'apv-1': { kind: 'server', final: false, detail: 'locked' } } })
    expect(html).toContain('data-problem="server"')
    expect(html).toContain('The server could not record this decision (locked)')
  })

  it('a settled item is not counted as held', () => {
    const html = view({
      approvals: [{ ...HELD, status: 'approved' }],
      problems: { 'apv-1': { kind: 'already_decided', final: true } },
    })
    expect(html).not.toMatch(/Held for you<[^>]*>\s*<span[^>]*>1</)
  })

  it('the expired tab explains what expired means', () => {
    const html = view({ tab: 'expired', approvals: [] })
    expect(html).toContain('Nothing has expired')
    expect(html).toContain('no longer be approved')
  })

  it('Hebrew page', () => {
    const html = view({ text: approvalText('he'), language: 'he' })
    expect(html).toContain('אישורים')
    expect(html).toContain('ממתין לך')
    expect(html).toContain('אישור והרצה')
  })
})

function banner(outcome: DecisionResponse, language = 'en'): string {
  return renderToStaticMarkup(
    <OutcomeBanner outcome={outcome} now={NOW} text={approvalText(language)} onClose={noop} />,
  )
}

describe('OutcomeBanner', () => {
  const approved: DecisionResponse = { ...HELD, status: 'approved' }

  it('approved and done', () => {
    const html = banner({
      ...approved,
      execution: { executed: true, success: true, output: 'sent', error: null },
    })
    expect(html).toContain('data-outcome="succeeded"')
    expect(html).toContain('Approved and done: sent')
  })

  it('approved but failed: the error, in red, not "approved"', () => {
    const html = banner({
      ...approved,
      execution: { executed: true, success: false, output: '', error: 'SMTP refused' },
    })
    expect(html).toContain('data-outcome="failed"')
    expect(html).toContain('Approved, but it failed: SMTP refused')
    expect(html).toContain('border-red-400/30')
  })

  it('a pack approval whose application failed (legacy {error} shape)', () => {
    const html = banner({
      ...approved,
      action_type: 'pack_verify',
      action_name: null,
      execution: { error: 'Pack market/audit-missing is not installed' },
    })
    expect(html).toContain('data-outcome="failed"')
    expect(html).toContain('Pack market/audit-missing is not installed')
  })

  it('an approved action that did not run is a warning', () => {
    const html = banner({
      ...approved,
      execution: { executed: false, success: false, output: '', error: null },
    })
    expect(html).toContain('data-outcome="not_started"')
    expect(html).toContain('border-amber-400/30')
  })

  it('decision log: rendered only when the server reports it', () => {
    expect(banner({ ...approved, action_name: null })).not.toContain('data-decision-log')
    const logged = banner({ ...approved, action_name: null, decision_log: { logged: true } })
    expect(logged).toContain('data-decision-log="logged"')
    expect(logged).toContain('Added to the decision log.')
    const missed = banner({
      ...approved,
      action_name: null,
      decision_log: { logged: false, error: 'disk full' },
    })
    expect(missed).toContain('data-decision-log="missing"')
    expect(missed).toContain('Not added to the decision log: disk full')
  })

  it('Hebrew banner', () => {
    const html = banner(
      { ...approved, execution: { executed: true, success: false, output: '', error: 'x' } },
      'he',
    )
    expect(html).toContain('אושר, אבל הביצוע נכשל: x')
  })
})
