/**
 * Agent detail: pause, resume and the schedule editor are for roles that may
 * change agents (`system:write`, venture_scope.py), like the other pages
 * gated after the Codex audit (recommendation 7). Others see why.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { agentControlsGate } from '@/lib/permissions'
import { AgentDetailView, type AgentData } from './agent-detail'

const AGENT: AgentData = {
  key: 'site-payments',
  venture_key: 'tower-b',
  definition_path: 'systems/tower-b/A-agents/site-payments.md',
  definition: '# Site payments',
  status: 'idle',
  last_run_at: null,
  last_error: null,
  schedule_cron: null,
  schedule_interval_sec: null,
  next_run_at: null,
  recent_activity: [],
}

const noop = () => {}

function render(data: AgentData, role: string): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <AgentDetailView
        data={data}
        ventureKey="tower-b"
        gate={agentControlsGate({ role })}
        onPause={noop}
        onResume={noop}
        onScheduleSaved={noop}
      />
    </MemoryRouter>,
  )
}

describe('AgentDetailView', () => {
  it('an operator can pause and reschedule', () => {
    const html = render(AGENT, 'operator')
    expect(html).toContain('>Pause<')
    expect(html).toContain('Schedule Configuration')
    expect(html).not.toContain('data-gate="agent"')
  })

  it('a paused agent offers Resume', () => {
    const html = render({ ...AGENT, status: 'paused' }, 'operator')
    expect(html).toContain('>Resume<')
    expect(html).not.toContain('>Pause<')
  })

  it('a viewer sees the agent, no controls, and why', () => {
    const html = render({ ...AGENT, status: 'paused' }, 'viewer')
    expect(html).toContain('data-gate="agent"')
    expect(html).toContain('View only: your role (viewer) can see this agent')
    expect(html).not.toContain('>Pause<')
    expect(html).not.toContain('>Resume<')
    expect(html).not.toContain('Schedule Configuration')
    // Still a full read view.
    expect(html).toContain('site-payments')
    expect(html).toContain('Recent Activity (0)')
  })

  it('back is a real link to the venture', () => {
    expect(render(AGENT, 'viewer')).toContain('href="/ventures/tower-b"')
  })
})
