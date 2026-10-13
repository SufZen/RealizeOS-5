/**
 * Codex audit N12: the Overview's Agents figure counts configured agents, so a
 * fresh install (no runtime-state rows yet) matches the venture cards.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentFigures } from '@/lib/dashboard-figures'
import { OverviewFigures } from './overview'

afterEach(() => {
  vi.unstubAllGlobals()
})

const FRESH = {
  ventures: [{ agent_count: 2 }, { agent_count: 2 }],
  agent_total: 4,
  agent_summary: { idle: 4, running: 0, paused: 0, error: 0 },
}

describe('agentFigures', () => {
  it('fresh install: the headline equals the configured agents', () => {
    expect(agentFigures(FRESH)).toEqual({ total: 4, running: 0, errors: 0 })
  })

  it('an older server without agent_total: still the configured agents, not runtime rows', () => {
    const old = { ventures: FRESH.ventures, agent_summary: { idle: 0, running: 0, error: 0 } }
    expect(agentFigures(old).total).toBe(4)
  })

  it('running and errors come from runtime state', () => {
    const busy = { ...FRESH, agent_summary: { idle: 2, running: 1, paused: 0, error: 1 } }
    expect(agentFigures(busy)).toEqual({ total: 4, running: 1, errors: 1 })
  })
})

describe('OverviewFigures', () => {
  it('renders the configured total', () => {
    // Reduced motion: the figure shows its value at once instead of counting up.
    vi.stubGlobal('window', { matchMedia: () => ({ matches: true }) })
    const html = renderToStaticMarkup(
      <OverviewFigures ventureCount={2} figures={agentFigures(FRESH)} />,
    )
    const values = [...html.matchAll(/rz-stat__value">([^<]*)</g)].map((m) => m[1])
    expect(values).toEqual(['2', '4', '0', '0'])
  })
})
