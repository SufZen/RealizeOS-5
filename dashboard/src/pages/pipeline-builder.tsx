import { useState, useCallback } from 'react'
import {
  GitBranch,
  Plus,
  Trash2,
  GripVertical,
  Play,
  Save,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Bot,
  Wrench,
  User,
  GitFork,
  ChevronDown,
  Loader2,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type StepType = 'agent' | 'tool' | 'condition' | 'human'

interface PipelineStep {
  id: string
  type: StepType
  label: string
  agent?: string
  tool?: string
  prompt?: string
  question?: string
  condition_field?: string
  inject_context?: string[]
}

interface Pipeline {
  id: string
  name: string
  description: string
  steps: PipelineStep[]
  version: number
  updated_at?: string
}

interface PipelinesData {
  pipelines: Pipeline[]
}

interface VenturesData {
  ventures: Array<{ key: string; name: string }>
}

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const STEP_TYPE_META: Record<StepType, { icon: typeof Bot; color: string; bg: string }> = {
  agent:     { icon: Bot,     color: 'text-blue-400',   bg: 'bg-blue-400/10 border-blue-400/20' },
  tool:      { icon: Wrench,  color: 'text-emerald-400', bg: 'bg-emerald-400/10 border-emerald-400/20' },
  condition: { icon: GitFork, color: 'text-amber-400',  bg: 'bg-amber-400/10 border-amber-400/20' },
  human:     { icon: User,    color: 'text-purple-400', bg: 'bg-purple-400/10 border-purple-400/20' },
}

const AVAILABLE_AGENTS = ['orchestrator', 'writer', 'reviewer', 'analyst', 'custom']
const AVAILABLE_TOOLS = ['web_search', 'gmail_send', 'google_calendar', 'google_sheets', 'browser']

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

export default function PipelineBuilderPage() {
  const { data, loading, error } = useApi<PipelinesData>('/pipelines')
  const { data: venturesData } = useApi<VenturesData>('/ventures')
  const [selectedVenture, setSelectedVenture] = useState('')
  const [activeTab, setActiveTab] = useState<'builder' | 'library'>('builder')

  // Local pipeline state
  const [pipeline, setPipeline] = useState<Pipeline>({
    id: '',
    name: 'New Pipeline',
    description: '',
    steps: [],
    version: 1,
  })
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [testResult, setTestResult] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)

  /* ---- Step CRUD ---- */

  const addStep = useCallback((type: StepType) => {
    const stepId = `step_${Date.now().toString(36)}`
    const defaultLabels: Record<StepType, string> = {
      agent: 'Agent Call',
      tool: 'Tool Action',
      condition: 'Branch',
      human: 'User Input',
    }
    const newStep: PipelineStep = {
      id: stepId,
      type,
      label: defaultLabels[type],
      agent: type === 'agent' ? 'orchestrator' : undefined,
      tool: type === 'tool' ? 'web_search' : undefined,
      question: type === 'human' ? 'Please confirm to continue.' : undefined,
    }
    setPipeline((p) => ({ ...p, steps: [...p.steps, newStep] }))
  }, [])

  const removeStep = useCallback((stepId: string) => {
    setPipeline((p) => ({ ...p, steps: p.steps.filter((s) => s.id !== stepId) }))
  }, [])

  const updateStep = useCallback((stepId: string, updates: Partial<PipelineStep>) => {
    setPipeline((p) => ({
      ...p,
      steps: p.steps.map((s) => (s.id === stepId ? { ...s, ...updates } : s)),
    }))
  }, [])

  const moveStep = useCallback((stepId: string, direction: 'up' | 'down') => {
    setPipeline((p) => {
      const idx = p.steps.findIndex((s) => s.id === stepId)
      if (idx < 0) return p
      const newIdx = direction === 'up' ? idx - 1 : idx + 1
      if (newIdx < 0 || newIdx >= p.steps.length) return p
      const newSteps = [...p.steps]
      ;[newSteps[idx], newSteps[newIdx]] = [newSteps[newIdx], newSteps[idx]]
      return { ...p, steps: newSteps }
    })
  }, [])

  /* ---- Save ---- */

  const handleSave = useCallback(async () => {
    if (!selectedVenture) return
    setSaveStatus('saving')
    try {
      await api.post('/pipelines', { ...pipeline, venture_key: selectedVenture })
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 2000)
    } catch {
      setSaveStatus('error')
    }
  }, [pipeline, selectedVenture])

  /* ---- Test run ---- */

  const handleTest = useCallback(async () => {
    if (!selectedVenture || pipeline.steps.length === 0) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post<{ result: string }>('/pipelines/test', {
        ...pipeline,
        venture_key: selectedVenture,
      })
      setTestResult(res.result)
    } catch (err) {
      setTestResult(`Error: ${err instanceof Error ? err.message : 'Test failed'}`)
    } finally {
      setTesting(false)
    }
  }, [pipeline, selectedVenture])

  /* ---- Load from library ---- */

  const loadPipeline = useCallback((p: Pipeline) => {
    setPipeline(p)
    setActiveTab('builder')
  }, [])

  /* ---- Render ---- */

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <GitBranch className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Pipeline Builder</h1>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedVenture}
            onChange={(e) => setSelectedVenture(e.target.value)}
            className="appearance-none bg-surface-800 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
          >
            <option value="">Select venture...</option>
            {venturesData?.ventures.map((v) => (
              <option key={v.key} value={v.key}>{v.name || v.key}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {(['builder', 'library'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-2 text-sm font-medium border-b-2 transition-colors capitalize',
              activeTab === tab
                ? 'border-brand-400 text-brand-400'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 'builder' ? (
        <>
          {/* Pipeline meta */}
          <div className="rounded-xl border border-border bg-card p-5">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Pipeline Name</label>
                <input
                  value={pipeline.name}
                  onChange={(e) => setPipeline((p) => ({ ...p, name: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-surface-800 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground block mb-1">Description</label>
                <input
                  value={pipeline.description}
                  onChange={(e) => setPipeline((p) => ({ ...p, description: e.target.value }))}
                  className="w-full rounded-lg border border-border bg-surface-800 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
                  placeholder="What does this pipeline do?"
                />
              </div>
            </div>
          </div>

          {/* Step toolbox */}
          <div className="flex flex-wrap gap-2">
            <span className="text-xs text-muted-foreground self-center mr-1">Add step:</span>
            {(Object.entries(STEP_TYPE_META) as [StepType, typeof STEP_TYPE_META[StepType]][]).map(
              ([type, meta]) => {
                const Icon = meta.icon
                return (
                  <button
                    key={type}
                    onClick={() => addStep(type)}
                    className={cn(
                      'flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-all',
                      'hover:scale-105 active:scale-95',
                      meta.bg, meta.color,
                    )}
                  >
                    <Plus className="h-3 w-3" />
                    <Icon className="h-3.5 w-3.5" />
                    <span className="capitalize">{type}</span>
                  </button>
                )
              },
            )}
          </div>

          {/* Pipeline canvas */}
          <div className="rounded-xl border border-border bg-card p-5 min-h-[200px]">
            {pipeline.steps.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-muted-foreground gap-2">
                <GitBranch className="h-8 w-8 opacity-30" />
                <p className="text-sm">Add steps to build your agent pipeline</p>
                <p className="text-xs">Steps execute in sequence — each step's output feeds into the next</p>
              </div>
            ) : (
              <div className="space-y-1">
                {pipeline.steps.map((step, idx) => (
                  <StepCard
                    key={step.id}
                    step={step}
                    index={idx}
                    total={pipeline.steps.length}
                    allSteps={pipeline.steps}
                    onUpdate={(updates) => updateStep(step.id, updates)}
                    onRemove={() => removeStep(step.id)}
                    onMove={(dir) => moveStep(step.id, dir)}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleSave}
              disabled={!selectedVenture || saveStatus === 'saving'}
              className={cn(
                'flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg font-medium transition-colors',
                saveStatus === 'saved'
                  ? 'bg-green-400/10 text-green-400 border border-green-400/20'
                  : 'bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40',
              )}
            >
              {saveStatus === 'saving' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : saveStatus === 'saved' ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <Save className="h-4 w-4" />
              )}
              {saveStatus === 'saved' ? 'Saved' : 'Save Pipeline'}
            </button>

            <button
              onClick={handleTest}
              disabled={!selectedVenture || pipeline.steps.length === 0 || testing}
              className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg border border-border text-foreground hover:bg-surface-700 disabled:opacity-40 transition-colors"
            >
              {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              Test Run
            </button>

            {saveStatus === 'error' && (
              <span className="flex items-center gap-1 text-xs text-red-400">
                <AlertCircle className="h-3.5 w-3.5" />
                Save failed
              </span>
            )}
          </div>

          {/* Test result */}
          {testResult && (
            <div className="rounded-xl border border-border bg-card p-5">
              <h3 className="text-sm font-semibold text-foreground mb-2">Test Result</h3>
              <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono bg-surface-900 rounded-lg p-4 max-h-48 overflow-auto">
                {testResult}
              </pre>
            </div>
          )}
        </>
      ) : (
        /* Library tab */
        <PipelineLibrary
          pipelines={data?.pipelines ?? []}
          loading={loading}
          error={error}
          onSelect={loadPipeline}
        />
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Step Card                                                           */
/* ------------------------------------------------------------------ */

interface StepCardProps {
  step: PipelineStep
  index: number
  total: number
  allSteps: PipelineStep[]
  onUpdate: (updates: Partial<PipelineStep>) => void
  onRemove: () => void
  onMove: (dir: 'up' | 'down') => void
}

function StepCard({ step, index, total, allSteps, onUpdate, onRemove, onMove }: StepCardProps) {
  const [expanded, setExpanded] = useState(false)
  const meta = STEP_TYPE_META[step.type]
  const Icon = meta.icon

  return (
    <>
      {/* Connector arrow */}
      {index > 0 && (
        <div className="flex justify-center py-0.5">
          <ArrowRight className="h-3.5 w-3.5 text-surface-600 rotate-90" />
        </div>
      )}

      <div className={cn('rounded-xl border p-4 transition-all', meta.bg)}>
        {/* Header row */}
        <div className="flex items-center gap-3">
          <button
            className="cursor-grab text-muted-foreground hover:text-foreground"
            title="Drag to reorder"
            onClick={() => {}} // Drag placeholder
          >
            <GripVertical className="h-4 w-4" />
          </button>

          <div className={cn('flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium', meta.color)}>
            <Icon className="h-3.5 w-3.5" />
            <span className="capitalize">{step.type}</span>
          </div>

          <input
            value={step.label}
            onChange={(e) => onUpdate({ label: e.target.value })}
            className="flex-1 bg-transparent border-none text-sm text-foreground font-medium focus:outline-none"
            placeholder="Step label"
          />

          <div className="flex items-center gap-1">
            <button
              onClick={() => onMove('up')}
              disabled={index === 0}
              className="p-1 rounded text-muted-foreground hover:text-foreground disabled:opacity-30"
              title="Move up"
            >
              <ChevronDown className="h-3.5 w-3.5 rotate-180" />
            </button>
            <button
              onClick={() => onMove('down')}
              disabled={index === total - 1}
              className="p-1 rounded text-muted-foreground hover:text-foreground disabled:opacity-30"
              title="Move down"
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={() => setExpanded(!expanded)}
              className="p-1 rounded text-muted-foreground hover:text-foreground"
              title="Expand"
            >
              <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
            </button>
            <button
              onClick={onRemove}
              className="p-1 rounded text-muted-foreground hover:text-red-400"
              title="Remove"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Expanded config */}
        {expanded && (
          <div className="mt-3 pt-3 border-t border-white/5 space-y-3">
            {step.type === 'agent' && (
              <>
                <div>
                  <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Agent</label>
                  <select
                    value={step.agent ?? ''}
                    onChange={(e) => onUpdate({ agent: e.target.value })}
                    className="w-full rounded-lg border border-border bg-surface-900 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
                  >
                    {AVAILABLE_AGENTS.map((a) => (
                      <option key={a} value={a}>{a}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Prompt Override</label>
                  <textarea
                    value={step.prompt ?? ''}
                    onChange={(e) => onUpdate({ prompt: e.target.value })}
                    rows={2}
                    className="w-full rounded-lg border border-border bg-surface-900 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400 resize-none font-mono"
                    placeholder="Optional prompt template for this step"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Inject Context From</label>
                  <div className="flex flex-wrap gap-1.5">
                    {allSteps
                      .filter((s) => s.id !== step.id)
                      .map((s) => {
                        const isSelected = step.inject_context?.includes(s.id) ?? false
                        return (
                          <button
                            key={s.id}
                            onClick={() => {
                              const ctx = step.inject_context ?? []
                              onUpdate({
                                inject_context: isSelected
                                  ? ctx.filter((c) => c !== s.id)
                                  : [...ctx, s.id],
                              })
                            }}
                            className={cn(
                              'px-2 py-0.5 text-[10px] rounded border transition-colors',
                              isSelected
                                ? 'border-brand-400 text-brand-400 bg-brand-400/10'
                                : 'border-border text-muted-foreground hover:text-foreground',
                            )}
                          >
                            {s.label}
                          </button>
                        )
                      })}
                    {allSteps.length <= 1 && (
                      <span className="text-[10px] text-muted-foreground italic">No other steps yet</span>
                    )}
                  </div>
                </div>
              </>
            )}

            {step.type === 'tool' && (
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Tool</label>
                <select
                  value={step.tool ?? ''}
                  onChange={(e) => onUpdate({ tool: e.target.value })}
                  className="w-full rounded-lg border border-border bg-surface-900 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
                >
                  {AVAILABLE_TOOLS.map((t) => (
                    <option key={t} value={t}>{t}</option>
                  ))}
                </select>
              </div>
            )}

            {step.type === 'condition' && (
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Condition Field</label>
                <input
                  value={step.condition_field ?? ''}
                  onChange={(e) => onUpdate({ condition_field: e.target.value })}
                  className="w-full rounded-lg border border-border bg-surface-900 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400 font-mono"
                  placeholder="e.g. step_result.approved"
                />
              </div>
            )}

            {step.type === 'human' && (
              <div>
                <label className="text-[10px] text-muted-foreground uppercase tracking-wider block mb-1">Question</label>
                <textarea
                  value={step.question ?? ''}
                  onChange={(e) => onUpdate({ question: e.target.value })}
                  rows={2}
                  className="w-full rounded-lg border border-border bg-surface-900 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400 resize-none"
                  placeholder="What should we ask the user?"
                />
              </div>
            )}
          </div>
        )}
      </div>
    </>
  )
}

/* ------------------------------------------------------------------ */
/* Pipeline Library                                                    */
/* ------------------------------------------------------------------ */

interface PipelineLibraryProps {
  pipelines: Pipeline[]
  loading: boolean
  error: string | null
  onSelect: (p: Pipeline) => void
}

function PipelineLibrary({ pipelines, loading, error, onSelect }: PipelineLibraryProps) {
  if (loading) {
    return <div className="flex items-center justify-center h-40 text-muted-foreground">Loading pipelines...</div>
  }
  if (error) {
    return (
      <div className="flex items-center justify-center h-40 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load pipelines
      </div>
    )
  }
  if (pipelines.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-40 text-muted-foreground gap-2">
        <GitBranch className="h-8 w-8 opacity-30" />
        <p className="text-sm">No saved pipelines yet</p>
        <p className="text-xs">Create one in the Builder tab above</p>
      </div>
    )
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {pipelines.map((p) => (
        <button
          key={p.id}
          onClick={() => onSelect(p)}
          className="rounded-xl border border-border bg-card p-5 text-left hover:border-brand-400/50 transition-colors group"
        >
          <h3 className="text-sm font-semibold text-foreground group-hover:text-brand-400 transition-colors">
            {p.name}
          </h3>
          {p.description && (
            <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{p.description}</p>
          )}
          <div className="flex items-center gap-3 mt-3">
            <span className="text-[10px] text-muted-foreground">
              {p.steps.length} step{p.steps.length !== 1 ? 's' : ''}
            </span>
            <span className="text-[10px] text-muted-foreground">v{p.version}</span>
            {p.updated_at && (
              <span className="text-[10px] text-muted-foreground ml-auto">
                {new Date(p.updated_at).toLocaleDateString()}
              </span>
            )}
          </div>
          <div className="flex gap-1.5 mt-2">
            {p.steps.map((s) => {
              const m = STEP_TYPE_META[s.type]
              const SIcon = m.icon
              return (
                <span key={s.id} className={cn('p-1 rounded', m.bg)} title={s.label}>
                  <SIcon className={cn('h-3 w-3', m.color)} />
                </span>
              )
            })}
          </div>
        </button>
      ))}
    </div>
  )
}
