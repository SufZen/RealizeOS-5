/**
 * Codex audit N11 + N04 (UI): an expired item can't be decided, a refused or
 * failed decision is said on the card, and history shows what really ran.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ApprovalCard, type Approval } from './approval-card'

const NOW = Date.parse('2026-10-13T12:00:00Z')

const HELD: Approval = {
  id: 'apv-1',
  venture_key: 'tower-b',
  agent_key: 'site-payments',
  action_type: 'send_email',
  action_name: 'send_email',
  status: 'pending',
  created_at: '2026-10-13T09:00:00Z',
  expires_at: '2026-10-13T13:00:00.000000Z',
  params_json: JSON.stringify({ to: 'client@acme.io' }),
}

const noop = () => {}

/** Tailwind classes tied to a physical side, which would not flip in RTL. */
const PHYSICAL_CLASS =
  /(?:^|\s)-?(?:ml|mr|pl|pr|left|right|border-l|border-r|rounded-l|rounded-r)-|(?:^|\s)text-(?:left|right)(?:\s|$)/

function classesOf(html: string): string[] {
  return [...html.matchAll(/class="([^"]*)"/g)].map((m) => m[1]!)
}

function buttons(html: string): string[] {
  return [...html.matchAll(/<button([^>]*)>(.*?)<\/button>/g)].map((m) => `${m[1]}|${m[2]}`)
}

describe('ApprovalCard', () => {
  it('a held item can be decided', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard approval={HELD} now={NOW} onApprove={noop} onReject={noop}>
        <input aria-label="Note for this decision" />
      </ApprovalCard>,
    )
    expect(html).toContain('aria-label="Send email: Held"')
    expect(html).toContain('Expires in 1 h')
    const [reject, approve] = buttons(html)
    expect(reject).toContain('Reject')
    expect(reject).not.toContain('disabled')
    expect(approve).toContain('Approve &amp; run')
    expect(approve).not.toContain('disabled')
    expect(html).toContain('Note for this decision')
  })

  it('an item whose time ran out is expired: decisions disabled, and it says why', () => {
    const later = Date.parse('2026-10-13T13:00:01Z')
    const html = renderToStaticMarkup(
      <ApprovalCard approval={HELD} now={later} onApprove={noop} onReject={noop}>
        <input aria-label="Note for this decision" />
      </ApprovalCard>,
    )
    expect(html).toContain('aria-label="Send email: Expired"')
    expect(html).not.toContain('rz-held')
    expect(html).toContain('This request expired before anyone decided it')
    const all = buttons(html)
    expect(all).toHaveLength(2)
    for (const b of all) {
      expect(b).toContain('disabled')
      expect(b).toContain('aria-describedby')
    }
    expect(html).not.toContain('Note for this decision')
  })

  it('a listed expired item has no decision controls at all', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={{ ...HELD, status: 'expired', expired: true }}
        now={NOW}
        onApprove={noop}
        onReject={noop}
      />,
    )
    expect(html).toContain('Send email: Expired')
    expect(html).toContain('can no longer be approved or rejected')
    expect(buttons(html)).toHaveLength(0)
  })

  it('a failed decision is shown inline, and the item stays actionable', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={HELD}
        now={NOW}
        onApprove={noop}
        onReject={noop}
        problem={{ kind: 'network', final: false }}
        onDismissProblem={noop}
      />,
    )
    expect(html).toContain('role="alert"')
    expect(html).toContain('data-problem="network"')
    expect(html).toContain('The server could not be reached')
    expect(buttons(html).filter((b) => b.includes('Approve'))[0]).not.toContain('disabled')
  })

  it('someone else decided first: the card shows their decision and no controls', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={{ ...HELD, status: 'approved', decided_by: 'dana@acme.io' }}
        now={NOW}
        onApprove={noop}
        onReject={noop}
        problem={{
          kind: 'already_decided',
          final: true,
          approval: { status: 'approved', decided_by: 'dana@acme.io' },
        }}
      />,
    )
    expect(html).toContain('Someone else already decided this (approved by dana@acme.io)')
    expect(html).toContain('Decided by <bdi>dana@acme.io</bdi>')
    expect(buttons(html).some((b) => b.includes('Approve'))).toBe(false)
  })

  it('history: approved but failed shows the error, not success', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={{
          ...HELD,
          status: 'approved',
          executed_at: '2026-10-13T10:00:00Z',
          execution_status: 'failed',
          error: 'Pack market/audit-missing is not installed',
        }}
        now={NOW}
      />,
    )
    expect(html).toContain('data-outcome="failed"')
    expect(html).toContain(
      'Approved, but it failed: Pack market/audit-missing is not installed. It is not retried',
    )
    expect(html).not.toContain('Approved and done')
  })

  it('history: claimed means unknown, and a person has to check', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={{
          ...HELD,
          status: 'approved',
          executed_at: '2026-10-13T10:00:00Z',
          execution_status: 'claimed',
        }}
        now={NOW}
      />,
    )
    expect(html).toContain('data-outcome="unknown"')
    expect(html).toContain('a person has to check')
  })

  it('history: succeeded shows the stored output', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={{
          ...HELD,
          status: 'approved',
          executed_at: '2026-10-13T10:00:00Z',
          execution_status: 'succeeded',
          result_json: JSON.stringify({ output: 'Email sent to client@acme.io' }),
        }}
        now={NOW}
      />,
    )
    expect(html).toContain('data-outcome="succeeded"')
    expect(html).toContain('Approved and done: Email sent to client@acme.io')
  })

  it('history: an approved action that never ran is not shown as done', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard approval={{ ...HELD, status: 'approved' }} now={NOW} />,
    )
    expect(html).toContain('data-outcome="not_started"')
  })

  it('an answered question reads as answered, not expired', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={{ ...HELD, action_type: 'skill_input', action_name: null, status: 'answered' }}
        now={NOW}
      />,
    )
    expect(html).toContain(': Answered"')
    expect(html).not.toContain('Expired')
  })

  it('a viewer sees why there are no decision controls', () => {
    const html = renderToStaticMarkup(
      <ApprovalCard
        approval={HELD}
        now={NOW}
        blockedReason="View only: your role (viewer) can see approvals but can’t approve or reject them."
      />,
    )
    expect(html).toContain('data-gate="decide"')
    expect(html).toContain('View only: your role (viewer)')
    expect(buttons(html)).toHaveLength(0)
  })

  it('Hebrew: expired and error states in Hebrew, mirror-safe', () => {
    const later = Date.parse('2026-10-13T13:00:01Z')
    const html = renderToStaticMarkup(
      <>
        <ApprovalCard approval={HELD} now={later} language="he" onApprove={noop} onReject={noop} />
        <ApprovalCard
          approval={HELD}
          now={NOW}
          language="he"
          onApprove={noop}
          onReject={noop}
          problem={{
            kind: 'already_decided',
            final: true,
            approval: { status: 'rejected', decided_by: 'דנה' },
          }}
        />
      </>,
    )
    expect(html).toContain('aria-label="שליחת מייל: פג תוקף"')
    expect(html).toContain('תוקף הבקשה פג לפני שמישהו החליט עליה')
    expect(html).toContain('מישהו אחר כבר החליט על הבקשה (נדחה ע״י דנה)')
    expect(html).toContain('dir="auto"')
    for (const cls of classesOf(html)) expect(cls).not.toMatch(PHYSICAL_CLASS)
  })
})
