/* eslint-disable react-refresh/only-export-components */
import { Settings, Shield, Cpu, Server, Database, RefreshCw } from 'lucide-react'
import { Toggle } from './shared'
import { cn } from '@/lib/utils'

export const FEATURE_LABELS: Record<string, string> = {
  activity_log: 'Activity Log — log all agent actions to SQLite',
  agent_lifecycle: 'Agent Lifecycle — track agent status (idle/running/paused/error)',
  heartbeats: 'Heartbeats — scheduled agent runs',
  approval_gates: 'Approval Gates — require human approval for consequential actions',
  review_pipeline: 'Review Pipeline — auto-route to reviewer agent',
  auto_memory: 'Auto Memory — log learnings after interactions',
  proactive_mode: 'Proactive Mode — include proactive layer in prompts',
  cross_system: 'Cross System — share context across all ventures',
}

export const GATE_LABELS: Record<string, string> = {
  send_email: 'Send Email',
  publish_content: 'Publish Content',
  external_api: 'External API Calls',
  create_event: 'Create Calendar Events',
  high_cost_llm: 'High-Cost LLM Calls',
}

interface Provider {
  name: string
  available: boolean
  models: string[]
}

interface SystemInfo {
  python_version: string
  db_size_bytes: number
  kb_file_count: number
  config_path: string
}

export function FeatureFlagsSection({ 
  features, saving, onToggle 
}: { 
  features: Record<string, boolean>; saving: boolean; onToggle: (k: string, v: boolean) => void 
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Settings className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Feature Flags</h2>
      </div>
      <div className="space-y-3">
        {Object.entries(FEATURE_LABELS).map(([key, label]) => (
          <div key={key} className="flex items-center justify-between gap-4">
            <span className="text-sm text-foreground">{label}</span>
            <Toggle
              checked={!!features[key]}
              onChange={(v) => onToggle(key, v)}
              disabled={saving}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export function GovernanceGatesSection({ 
  gates, saving, onToggle 
}: { 
  gates: Record<string, boolean>; saving: boolean; onToggle: (k: string, v: boolean) => void 
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Shield className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Governance Gates</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">Actions that require human approval before execution</p>
      <div className="space-y-3">
        {Object.entries(GATE_LABELS).map(([key, label]) => (
          <div key={key} className="flex items-center justify-between gap-4">
            <span className="text-sm text-foreground">{label}</span>
            <Toggle
              checked={!!gates[key]}
              onChange={(v) => onToggle(key, v)}
              disabled={saving}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export function LLMProvidersSection({ providers }: { providers: Provider[] }) {
  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Cpu className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">LLM Providers</h2>
      </div>
      {providers.length === 0 ? (
        <p className="text-sm text-muted-foreground">No providers registered</p>
      ) : (
        <div className="space-y-2">
          {providers.map((p) => (
            <div key={p.name} className="flex items-center justify-between gap-4">
              <div>
                <span className="text-sm text-foreground font-medium capitalize">{p.name}</span>
                {p.available && p.models.length > 0 && (
                  <span className="text-xs text-muted-foreground ml-2">
                    ({p.models.length} model{p.models.length !== 1 ? 's' : ''})
                  </span>
                )}
              </div>
              <span
                className={cn(
                  'text-xs px-2 py-0.5 rounded-full',
                  p.available && p.models.length > 0
                    ? 'bg-green-400/10 text-green-400'
                    : p.available
                    ? 'bg-amber-400/10 text-amber-400'
                    : 'bg-surface-700 text-muted-foreground',
                )}
              >
                {p.available && p.models.length > 0 ? 'Connected' : p.available ? 'Available' : 'Not configured'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function SystemInfoSection({ info }: { info: SystemInfo }) {
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Server className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">System Info</h2>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="text-muted-foreground">Python</div>
        <div className="text-foreground">{info.python_version}</div>
        <div className="text-muted-foreground">Database size</div>
        <div className="text-foreground">
          {info.db_size_bytes === 0
            ? <span className="text-muted-foreground italic">Empty — will initialize on first chat</span>
            : formatBytes(info.db_size_bytes)}
        </div>
        <div className="text-muted-foreground">KB files</div>
        <div className="text-foreground">{info.kb_file_count} markdown files</div>
      </div>
    </div>
  )
}

export function MaintenanceSection({ 
  saving, onReload, onReindex 
}: { 
  saving: boolean; onReload: () => void; onReindex: () => void 
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Database className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Maintenance</h2>
      </div>
      <div className="flex gap-3">
        <button
          onClick={onReload}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={cn('h-4 w-4', saving && 'animate-spin')} />
          Reload Config
        </button>
        <button
          onClick={onReindex}
          disabled={saving}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          <Database className={cn('h-4 w-4', saving && 'animate-spin')} />
          Reindex Knowledge Base
        </button>
      </div>
    </div>
  )
}
