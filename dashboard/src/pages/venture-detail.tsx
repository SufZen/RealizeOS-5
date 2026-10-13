import { useParams, useNavigate } from 'react-router-dom'
import { AlertCircle, ChevronRight, FileText, Check, Download } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { AgentStatusBadge, type AgentStatus } from '@/components/agent-status-badge'
import { OrgChart } from '@/components/org-chart'
import { KBBrowser } from '@/components/kb-browser'
import { cn } from '@/lib/utils'
import { TitleBlock } from '@/components/ui/title-block'
import { Panel } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { SkeletonCard } from '@/components/ui/skeleton'

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

/** The company brain's six parts. Quiet when present; only a missing part asks for attention. */
function FabricGrid({
  directories,
  completeness,
}: {
  directories: Record<string, FabricDir>
  completeness: number
}) {
  return (
    <Panel
      title="FABRIC structure"
      actions={
        <span className="text-xs tabular text-muted-foreground">{completeness}% complete</span>
      }
    >
      <div className="rz-progress mb-4" aria-hidden>
        <div className="rz-progress__bar" style={{ ['--_v' as string]: `${completeness}%` }} />
      </div>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
        {Object.entries(fabricLabels).map(([dirKey, { letter, name }]) => {
          const dir = directories[dirKey]
          const exists = dir?.exists ?? false
          const count = dir?.file_count ?? 0
          return (
            <div
              key={dirKey}
              className={cn(
                'flex items-center gap-3 rounded-[7px] border px-3 py-2.5',
                exists ? 'border-border bg-background/40' : 'border-dashed border-amber-400/50',
              )}
            >
              <span
                className={cn(
                  'grid h-8 w-8 shrink-0 place-items-center rounded-[5px] font-mono text-sm font-medium',
                  exists ? 'bg-surface-700 text-foreground' : 'bg-amber-400/10 text-amber-400',
                )}
                aria-hidden
              >
                {letter}
              </span>
              <div className="min-w-0">
                <div className="truncate text-[13px] font-medium text-foreground">{name}</div>
                <div className="text-xs text-subtle-foreground">
                  {exists ? (
                    <span className="inline-flex items-center gap-1">
                      <Check className="h-3 w-3 text-emerald-400" />
                      {count} files
                    </span>
                  ) : (
                    <span className="text-amber-400">Missing</span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </Panel>
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
  const { data } = useApi<OrgTreeResponse>(`/ventures/${ventureKey}/org-tree`)

  if (!data || data.tree.length === 0) return null

  const statusMap: Record<string, AgentStatus> = {}
  for (const a of agents) statusMap[a.key] = a.status

  return (
    <Panel title="Organization">
      <OrgChart tree={data.tree} ventureKey={ventureKey} agentStatuses={statusMap} />
    </Panel>
  )
}

export default function VentureDetailPage() {
  const { key } = useParams<{ key: string }>()
  const navigate = useNavigate()
  const { data, loading, error } = useApi<VentureData>(`/ventures/${key}`)

  if (loading) {
    return (
      <div className="grid gap-4" aria-busy="true" aria-label="Loading venture">
        <SkeletonCard />
        <SkeletonCard />
      </div>
    )
  }

  if (error) {
    return (
      <div
        role="alert"
        className="flex items-start gap-2 rounded-[10px] border border-red-400/30 bg-red-400/10 p-4 text-sm text-red-400"
      >
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <span>{error}</span>
      </div>
    )
  }

  if (!data) return null

  return (
    <div className="mx-auto max-w-[1240px]">
      <TitleBlock
        crumbs={[{ label: 'Ventures', to: '/ventures' }, { label: data.name }]}
        title={<span dir="auto">{data.name}</span>}
        description={data.description || undefined}
        reference={[data.key]}
        actions={
          <Button onClick={() => window.open(`/api/ventures/${data.key}/export`, '_blank')}>
            <Download aria-hidden />
            Export
          </Button>
        }
      />

      <div className="flex flex-col gap-6">
        <FabricGrid directories={data.fabric.directories} completeness={data.fabric.completeness} />

        <OrgChartSection ventureKey={data.key} agents={data.agents} />

        <div className="grid gap-6 lg:grid-cols-2">
          <Panel
            title={
              <span className="inline-flex items-center gap-2">
                Agents <Badge>{data.agents.length}</Badge>
              </span>
            }
            flush
          >
            {data.agents.length === 0 ? (
              <p className="m-0 p-4 text-sm text-muted-foreground">No agents defined.</p>
            ) : (
              <ul className="m-0 list-none divide-y divide-border p-0">
                {data.agents.map((agent) => (
                  <li key={agent.key}>
                    <button
                      type="button"
                      onClick={() =>
                        navigate(`/ventures/${key}/agents/${agent.key}`, { viewTransition: true })
                      }
                      className="group flex w-full items-center gap-3 px-4 py-3 text-start transition-colors hover:bg-surface-700/50"
                    >
                      <span className="rz-avatar rz-avatar--agent rz-avatar--sm" aria-hidden>
                        {agent.key.slice(0, 2).toUpperCase()}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-foreground">
                          {agent.key}
                        </span>
                        {agent.last_run_at && (
                          <span className="block text-xs text-subtle-foreground">
                            Last run: {new Date(agent.last_run_at).toLocaleString()}
                          </span>
                        )}
                      </span>
                      <AgentStatusBadge status={agent.status} />
                      <ChevronRight className="h-4 w-4 text-subtle-foreground opacity-0 transition-opacity group-hover:opacity-100 rtl:rotate-180" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            title={
              <span className="inline-flex items-center gap-2">
                Skills <Badge>{data.skills.length}</Badge>
              </span>
            }
            flush
          >
            {data.skills.length === 0 ? (
              <p className="m-0 p-4 text-sm text-muted-foreground">No skills defined.</p>
            ) : (
              <ul className="m-0 list-none divide-y divide-border p-0">
                {data.skills.map((skill) => (
                  <li key={skill.name} className="flex items-center gap-3 px-4 py-3">
                    <FileText className="h-4 w-4 shrink-0 text-subtle-foreground" />
                    <span className="min-w-0 flex-1 truncate text-sm">
                      <span className="font-medium text-foreground">{skill.name}</span>
                      <span className="ms-2 text-xs text-subtle-foreground">{skill.version}</span>
                    </span>
                    <Badge>{skill.task_type}</Badge>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>

        <section aria-labelledby="vd-kb">
          <h2 id="vd-kb" className="mb-3 text-[15px] font-semibold text-foreground">
            Knowledge base
          </h2>
          <KBBrowser ventureKey={data.key} />
        </section>
      </div>
    </div>
  )
}
