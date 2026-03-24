import { useState, useEffect } from 'react'
import { Code, Loader2, ShieldCheck, AlertTriangle, Terminal, GitBranch, HelpCircle, RotateCcw } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useTour } from '@/components/tour-provider'
import { Toggle } from './shared'

interface DevModeStatus {
  enabled: boolean
  protection_level: string
  available_levels: string[]
  connected_tools: { key: string; name: string; context_file: string; active: boolean }[]
  last_snapshot: { tag: string; timestamp: string; message: string } | null
}

interface HealthCheck {
  name: string
  status: string
  icon: string
  message: string
  details: string
}

export function HelpSection() {
  const { startTour } = useTour()

  function resetOnboarding() {
    try {
      localStorage.removeItem('realizeos_onboarding_complete')
      window.location.reload()
    } catch {
      // ignore
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <HelpCircle className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Help & Support</h2>
      </div>
      <p className="text-xs text-muted-foreground mb-4">Re-run the guided tour or onboarding wizard to learn about RealizeOS features</p>
      <div className="flex gap-3">
        <button
          onClick={startTour}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 transition-colors"
        >
          <RotateCcw className="h-4 w-4" />
          Restart Tour
        </button>
        <button
          onClick={resetOnboarding}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 transition-colors"
        >
          <RotateCcw className="h-4 w-4" />
          Reset Onboarding
        </button>
      </div>
    </div>
  )
}

export function DevModeSection() {
  const [status, setStatus] = useState<DevModeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [showAcknowledgment, setShowAcknowledgment] = useState(false)
  const [ack1, setAck1] = useState(false)
  const [ack2, setAck2] = useState(false)
  const [ack3, setAck3] = useState(false)
  const [selectedLevel, setSelectedLevel] = useState('standard')
  const [healthResults, setHealthResults] = useState<HealthCheck[] | null>(null)
  const [runningCheck, setRunningCheck] = useState(false)
  const [generatingContext, setGeneratingContext] = useState(false)
  const [creatingSnapshot, setCreatingSnapshot] = useState(false)
  const [actionMessage, setActionMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  useEffect(() => {
    api.get<DevModeStatus>('/devmode/status')
      .then(res => {
        setStatus(res)
        setSelectedLevel(res.protection_level)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function toggleDevMode(enable: boolean) {
    if (enable && !showAcknowledgment) {
      setShowAcknowledgment(true)
      return
    }
    try {
      const res = await api.put<{ status: string; message: string }>('/devmode/toggle', {
        enabled: enable,
        protection_level: selectedLevel,
        acknowledged: ack1 && ack2 && ack3,
      })
      if (res.status === 'ok') {
        setStatus(prev => prev ? { ...prev, enabled: enable, protection_level: selectedLevel } : prev)
        setShowAcknowledgment(false)
        setActionMessage({ text: res.message, type: 'success' })
      } else {
        setActionMessage({ text: res.message, type: 'error' })
      }
    } catch {
      setActionMessage({ text: 'Failed to toggle Developer Mode', type: 'error' })
    }
  }

  async function runHealthCheck() {
    setRunningCheck(true)
    try {
      const res = await api.post<{ checks: HealthCheck[] }>('/devmode/check')
      setHealthResults(res.checks)
    } catch {
      setActionMessage({ text: 'Health check failed', type: 'error' })
    } finally {
      setRunningCheck(false)
    }
  }

  async function generateContext() {
    setGeneratingContext(true)
    try {
      const res = await api.post<{ count: number }>('/devmode/setup', { protection_level: selectedLevel })
      setActionMessage({ text: `Generated ${res.count} context file(s)`, type: 'success' })
      const updated = await api.get<DevModeStatus>('/devmode/status')
      setStatus(updated)
    } catch {
      setActionMessage({ text: 'Failed to generate context files', type: 'error' })
    } finally {
      setGeneratingContext(false)
    }
  }

  async function createSnapshot() {
    setCreatingSnapshot(true)
    try {
      const res = await api.post<{ tag: string }>('/devmode/snapshot')
      setActionMessage({ text: `Snapshot created: ${res.tag}`, type: 'success' })
    } catch {
      setActionMessage({ text: 'Failed to create snapshot', type: 'error' })
    } finally {
      setCreatingSnapshot(false)
    }
  }

  const levelDescriptions: Record<string, string> = {
    strict: 'All core + config files are read-only to AI tools',
    standard: 'Core engine protected, config editable with auto-backup',
    relaxed: 'Only security/db files protected, everything else open',
  }

  if (loading) {
    return (
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          <span className="text-sm text-muted-foreground">Loading Developer Mode...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-amber-500/30 bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Code className="h-5 w-5 text-amber-400" />
          <h2 className="text-lg font-semibold text-foreground">Advanced Developer Settings</h2>
          <span className="px-2 py-0.5 text-[10px] font-medium bg-amber-500/20 text-amber-400 rounded-full">ADVANCED</span>
        </div>
        <Toggle
          checked={status?.enabled ?? false}
          onChange={(checked) => toggleDevMode(checked)}
        />
      </div>

      <p className="text-xs text-muted-foreground mb-4">
        Enable integration with local AI coding tools (Claude Code, Gemini CLI, Cursor, etc.) for system development and extension authoring.
      </p>

      {showAcknowledgment && (
        <div className="mb-4 p-4 rounded-lg border border-amber-500/30 bg-amber-500/5">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <span className="text-sm font-medium text-amber-400">Before enabling Developer Mode</span>
          </div>
          <div className="space-y-2 mb-4">
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={ack1} onChange={e => setAck1(e.target.checked)} className="mt-0.5 accent-amber-400" />
              I understand that AI tools can modify system files and configurations
            </label>
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={ack2} onChange={e => setAck2(e.target.checked)} className="mt-0.5 accent-amber-400" />
              I will review all AI-generated changes before deploying
            </label>
            <label className="flex items-start gap-2 text-xs text-muted-foreground cursor-pointer">
              <input type="checkbox" checked={ack3} onChange={e => setAck3(e.target.checked)} className="mt-0.5 accent-amber-400" />
              I accept responsibility for modifications made by external AI tools
            </label>
          </div>
          <div className="flex gap-2">
            <button
              disabled={!(ack1 && ack2 && ack3)}
              onClick={() => toggleDevMode(true)}
              className="px-4 py-1.5 text-xs rounded-lg bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40 transition-colors"
            >
              Enable Developer Mode
            </button>
            <button
              onClick={() => { setShowAcknowledgment(false); setAck1(false); setAck2(false); setAck3(false) }}
              className="px-4 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:bg-surface-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {actionMessage && (
        <div className={cn('mb-4 px-3 py-2 rounded-lg text-xs', actionMessage.type === 'success' ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400')}>
          {actionMessage.text}
        </div>
      )}

      {status?.enabled && (
        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-foreground mb-1 block">Protection Level</label>
            <select
              value={selectedLevel}
              onChange={e => setSelectedLevel(e.target.value)}
              className="w-full px-3 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground"
            >
              {(status.available_levels || ['strict', 'standard', 'relaxed']).map(level => (
                <option key={level} value={level}>{level.charAt(0).toUpperCase() + level.slice(1)}</option>
              ))}
            </select>
            <p className="text-[10px] text-muted-foreground mt-1">{levelDescriptions[selectedLevel] || ''}</p>
          </div>

          <div>
            <label className="text-xs font-medium text-foreground mb-2 block">Connected AI Tools</label>
            <div className="grid grid-cols-2 gap-2">
              {(status.connected_tools || []).length > 0 ? (
                status.connected_tools.map(tool => (
                  <div key={tool.key} className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-800 border border-border">
                    <div className="h-2 w-2 rounded-full bg-green-400" />
                    <span className="text-xs text-foreground">{tool.name}</span>
                    <span className="text-[10px] text-muted-foreground ml-auto">{tool.context_file}</span>
                  </div>
                ))
              ) : (
                <p className="text-xs text-muted-foreground col-span-2">No context files generated yet. Click &quot;Generate Context Files&quot; below.</p>
              )}
            </div>
          </div>

          {status.last_snapshot && (
            <div className="px-3 py-2 rounded-lg bg-surface-800 border border-border">
              <div className="flex items-center gap-2">
                <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-xs text-foreground">Last snapshot: {status.last_snapshot.tag}</span>
                <span className="text-[10px] text-muted-foreground ml-auto">{status.last_snapshot.timestamp}</span>
              </div>
            </div>
          )}

          {healthResults && (
            <div className="space-y-1">
              <label className="text-xs font-medium text-foreground mb-1 block">Health Check Results</label>
              {healthResults.map((check, i) => (
                <div key={i} className="flex items-center gap-2 px-3 py-1.5 rounded bg-surface-800 text-xs">
                  <span>{check.icon}</span>
                  <span className="text-foreground font-medium">{check.name}</span>
                  <span className="text-muted-foreground">{check.message}</span>
                </div>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-2 border-t border-border">
            <button
              onClick={generateContext}
              disabled={generatingContext}
              className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {generatingContext ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Terminal className="h-3.5 w-3.5" />}
              Generate Context Files
            </button>
            <button
              onClick={runHealthCheck}
              disabled={runningCheck}
              className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {runningCheck ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              Run Health Check
            </button>
            <button
              onClick={createSnapshot}
              disabled={creatingSnapshot}
              className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {creatingSnapshot ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitBranch className="h-3.5 w-3.5" />}
              Create Snapshot
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
