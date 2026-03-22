import { useNavigate } from 'react-router-dom'
import { Bot } from 'lucide-react'
import { AgentStatusBadge, type AgentStatus } from '@/components/agent-status-badge'
import { cn } from '@/lib/utils'

interface OrgNode {
  key: string
  reports_to: string | null
  role: string
  children: OrgNode[]
}

interface OrgChartProps {
  tree: OrgNode[]
  ventureKey: string
  agentStatuses?: Record<string, AgentStatus>
  className?: string
}

function OrgNode({
  node,
  ventureKey,
  agentStatuses,
  depth = 0,
}: {
  node: OrgNode
  ventureKey: string
  agentStatuses?: Record<string, AgentStatus>
  depth?: number
}) {
  const navigate = useNavigate()
  const status = agentStatuses?.[node.key] || 'idle'

  return (
    <div className={cn(depth > 0 && 'ml-6 border-l border-border pl-4')}>
      <div
        onClick={() => navigate(`/ventures/${ventureKey}/agents/${node.key}`)}
        className="flex items-center gap-2 rounded-lg px-3 py-2 cursor-pointer hover:bg-surface-700/50 transition-colors"
      >
        <Bot className="h-4 w-4 text-muted-foreground shrink-0" />
        <span className="text-sm font-medium text-foreground">{node.key}</span>
        {node.role && (
          <span className="text-xs text-muted-foreground">{node.role}</span>
        )}
        <AgentStatusBadge status={status} className="ml-auto" />
      </div>
      {node.children.map((child) => (
        <OrgNode
          key={child.key}
          node={child}
          ventureKey={ventureKey}
          agentStatuses={agentStatuses}
          depth={depth + 1}
        />
      ))}
    </div>
  )
}

export function OrgChart({ tree, ventureKey, agentStatuses, className }: OrgChartProps) {
  if (tree.length === 0) {
    return (
      <p className={cn('text-sm text-muted-foreground', className)}>
        No hierarchy defined. Add <code>reports_to</code> to agent frontmatter.
      </p>
    )
  }

  return (
    <div className={cn('space-y-1', className)}>
      {tree.map((node) => (
        <OrgNode
          key={node.key}
          node={node}
          ventureKey={ventureKey}
          agentStatuses={agentStatuses}
        />
      ))}
    </div>
  )
}
