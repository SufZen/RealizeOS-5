/**
 * The Overview's headline figures (Codex audit N12). "Agents" is the number of
 * configured agents, the same count the venture cards show; running and error
 * counts come from runtime state. An agent that has never run has no runtime
 * row, so summing runtime states would undercount (a fresh install showed 0).
 */

export interface OverviewData {
  ventures: Array<{ agent_count: number }>
  /** Configured agents across the visible ventures (newer servers). */
  agent_total?: number
  /** Configured agents by runtime state. */
  agent_summary: Record<string, number>
}

export interface AgentFigures {
  total: number
  running: number
  errors: number
}

export function agentFigures(data: OverviewData): AgentFigures {
  const configured = data.ventures.reduce((sum, v) => sum + (v.agent_count || 0), 0)
  return {
    total: typeof data.agent_total === 'number' ? data.agent_total : configured,
    running: data.agent_summary.running || 0,
    errors: data.agent_summary.error || 0,
  }
}
