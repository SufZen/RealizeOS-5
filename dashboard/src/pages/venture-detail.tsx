import { useParams, useNavigate } from 'react-router-dom'
import {
  Briefcase,
  FolderOpen,
  AlertCircle,
  ChevronLeft,
  FileText,
  Check,
  X,
  Network,
  Download,
  BookOpen,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { AgentStatusBadge, type AgentStatus } from '@/components/agent-status-badge'
import { OrgChart } from '@/components/org-chart'
import { KBBrowser } from '@/components/kb-browser'
import { useApi as useApiRaw } from '@/hooks/use-api'
import { cn } from '@/lib/utils'

interface FabricDir {
  exists: boolean
  file_count: number
}

interface Agent {
  key: string
  definition_path: string
  status: AgentStatus
  last_run_at: string | null
  last_error: string | null
}

interface Skill {
  name: string
  version: string
  triggers: string[]
  task_type: string
}

interface VentureData {
  key: string
  name: string
  description: string
  fabric: {
    directories: Record<string, FabricDir>
    completeness: number
  }
  agents: Agent[]
  skills: Skill[]
}

const fabricLabels: Record<string, { letter: string; name: string }> = {
  'F-foundations': { letter: 'F', name: 'Foundations' },
  'A-agents': { letter: 'A', name: 'Agents' },
  'B-brain': { letter: 'B', name: 'Brain' },
  'R-routines': { letter: 'R', name: 'Routines' },
  'I-insights': { letter: 'I', name: 'Insights' },
  'C-creations': { letter: 'C', name: 'Creations' },
}

function FabricGrid({ directories, completeness }: { directories: Record<string, FabricDir>; completeness: number }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-foreground">FABRIC Structure</h3>
        <span className="text-xs text-muted-foreground">{completeness}% complete</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {Object.entries(fabricLabels).map(([dirKey, { letter, name }]) => {
          const dir = directories[dirKey]
          const exists = dir?.exists ?? false
          const count = dir?.file_count ?? 0
          return (
            <div
              key={dirKey}
              className={cn(
                'rounded-lg border p-3 text-center',
                exists && count > 0
                  ? 'border-brand-400/30 bg-brand-400/5'
                  : exists
                    ? 'border-border bg-card'
                    : 'border-border/50 bg-surface-800 opacity-50',
              )}
            >
              <div className="text-lg font-bold text-brand-400">{letter}</div>
              <div className="text-xs text-foreground">{name}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {exists ? (
                  <span className="inline-flex items-center gap-1">
                    <Check className="h-3 w-3 text-emerald-400" />
                    {count} files
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1">
                    <X className="h-3 w-3" />
                    missing
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface OrgTreeNode {
  key: string
  reports_to: string | null
  role: string
  children: OrgTreeNode[]
}

interface OrgTreeResponse {
  tree: OrgTreeNode[]
}

function OrgChartSection({ ventureKey, agents }: { ventureKey: string; agents: Agent[] }) {
  const { data } = useApiRaw<OrgTreeResponse>(`/ventures/${ventureKey}/org-tree`)

  if (!data || data.tree.length === 0) return null

  const statusMap: Record<string, AgentStatus> = {}
  for (const a of agents) statusMap[a.key] = a.status

  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <Network className="h-4 w-4 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Organization</h2>
      </div>
      <div className="rounded-xl border border-border bg-card p-4">
        <OrgChart tree={data.tree} ventureKey={ventureKey} agentStatuses={statusMap} />
      </div>
    </section>
  )
}

export default function VentureDetailPage() {
  const { key } = useParams<{ key: string }>()
  const navigate = useNavigate()
  const { data, loading, error } = useApi<VentureData>(`/ventures/${key}`)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Loading venture...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <button
          onClick={() => navigate('/ventures')}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground mb-2 transition-colors"
        >
          <ChevronLeft className="h-3 w-3" />
          Back to ventures
        </button>
        <div className="flex items-center gap-3">
          <Briefcase className="h-6 w-6 text-brand-400" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">{data.name}</h1>
            {data.description && (
              <p className="text-sm text-muted-foreground">{data.description}</p>
            )}
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => window.open(`/api/ventures/${data.key}/export`, '_blank')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:text-foreground transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              Export
            </button>
            <span className="text-xs text-muted-foreground font-mono">{data.key}</span>
          </div>
        </div>
      </div>

      {/* FABRIC */}
      <section className="rounded-xl border border-border bg-card p-4">
        <FabricGrid directories={data.fabric.directories} completeness={data.fabric.completeness} />
      </section>

      {/* Org Chart */}
      <OrgChartSection ventureKey={data.key} agents={data.agents} />

      {/* Agents */}
      <section>
        <h2 className="text-lg font-semibold text-foreground mb-3">
          Agents ({data.agents.length})
        </h2>
        <div className="space-y-2">
          {data.agents.map((agent) => (
            <div
              key={agent.key}
              onClick={() => navigate(`/ventures/${key}/agents/${agent.key}`)}
              className="flex items-center justify-between rounded-xl border border-border bg-card p-4 cursor-pointer hover:border-brand-400/50 transition-colors"
            >
              <div className="flex items-center gap-3">
                <FolderOpen className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium text-foreground">{agent.key}</span>
              </div>
              <div className="flex items-center gap-4">
                {agent.last_run_at && (
                  <span className="text-xs text-muted-foreground">
                    Last run: {new Date(agent.last_run_at).toLocaleString()}
                  </span>
                )}
                <AgentStatusBadge status={agent.status} />
              </div>
            </div>
          ))}
          {data.agents.length === 0 && (
            <p className="text-muted-foreground text-sm">No agents defined.</p>
          )}
        </div>
      </section>

      {/* Skills */}
      <section>
        <h2 className="text-lg font-semibold text-foreground mb-3">
          Skills ({data.skills.length})
        </h2>
        <div className="space-y-2">
          {data.skills.map((skill) => (
            <div
              key={skill.name}
              className="flex items-center justify-between rounded-xl border border-border bg-card p-4"
            >
              <div className="flex items-center gap-3">
                <FileText className="h-4 w-4 text-muted-foreground" />
                <div>
                  <span className="text-sm font-medium text-foreground">{skill.name}</span>
                  <span className="text-xs text-muted-foreground ml-2">{skill.version}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs bg-surface-700 text-muted-foreground px-2 py-0.5 rounded">
                  {skill.task_type}
                </span>
              </div>
            </div>
          ))}
          {data.skills.length === 0 && (
            <p className="text-muted-foreground text-sm">No skills defined.</p>
          )}
        </div>
      </section>

      {/* Knowledge Base */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <BookOpen className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">Knowledge Base</h2>
        </div>
        <KBBrowser ventureKey={data.key} />
      </section>
    </div>
  )
}
