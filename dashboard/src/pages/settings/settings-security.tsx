import { useState, useEffect } from 'react'
import { ShieldCheck, Loader2, Activity } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface SecuritySectionProps {
  saving: boolean
  setSaving: (v: boolean) => void
  setStatus: (v: { message: string; type: 'success' | 'error' } | null) => void
}

export function SecuritySection({ saving, setSaving, setStatus }: SecuritySectionProps) {
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<{
    passed: number; warnings: number; critical: number; total: number;
    checks: Array<{ name: string; status: string; detail: string }>
  } | null>(null)
  const [auditEvents, setAuditEvents] = useState<Array<{
    event_type: string; user: string; detail: string; timestamp: string
  }>>([])
  const [showAudit, setShowAudit] = useState(false)

  useEffect(() => {
    api.get<{ scan: typeof scanResult }>('/security/status')
      .then(res => { if (res.scan) setScanResult(res.scan) })
      .catch(() => {})
    api.get<{ events: typeof auditEvents }>('/security/events?limit=20')
      .then(res => setAuditEvents(res.events || []))
      .catch(() => {})
  }, [])

  async function runScan() {
    setScanning(true)
    setSaving(true)
    setStatus(null)
    try {
      const res = await api.post<{ issues: number; report: string; scan: typeof scanResult }>('/security/scan')
      if (res.scan) setScanResult(res.scan)
      setStatus({
        message: res.issues === 0 ? 'Security scan passed — no issues found' : `Scan found ${res.issues} issue(s)`,
        type: res.issues === 0 ? 'success' : 'error',
      })
    } catch (err) {
      setStatus({ message: err instanceof Error ? err.message : 'Security scan failed', type: 'error' })
    } finally {
      setScanning(false)
      setSaving(false)
    }
  }

  const statusColor = (s: string) => {
    if (s === 'pass') return 'text-emerald-400'
    if (s === 'critical') return 'text-red-400'
    return 'text-amber-400'
  }
  const statusIcon = (s: string) => {
    if (s === 'pass') return '✓'
    if (s === 'critical') return '✕'
    return '⚠'
  }

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-brand-400" />
          <h2 className="text-lg font-semibold text-foreground">Security Posture</h2>
        </div>
        <button
          onClick={runScan}
          disabled={saving || scanning}
          className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
        >
          {scanning ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
          {scanning ? 'Scanning...' : 'Run Scan'}
        </button>
      </div>

      {scanResult && (
        <>
          <div className="grid grid-cols-4 gap-3 mb-4">
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Total Checks</p>
              <p className="text-xl font-bold text-foreground">{scanResult.total}</p>
            </div>
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Passed</p>
              <p className="text-xl font-bold text-emerald-400">{scanResult.passed}</p>
            </div>
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Warnings</p>
              <p className="text-xl font-bold text-amber-400">{scanResult.warnings}</p>
            </div>
            <div className="rounded-lg bg-surface-800 p-3 text-center">
              <p className="text-xs text-muted-foreground">Critical</p>
              <p className="text-xl font-bold text-red-400">{scanResult.critical}</p>
            </div>
          </div>

          <div className="rounded-lg border border-border overflow-hidden mb-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-surface-800">
                  <th className="text-left px-3 py-2 text-xs text-muted-foreground font-medium">Check</th>
                  <th className="text-left px-3 py-2 text-xs text-muted-foreground font-medium w-16">Status</th>
                  <th className="text-left px-3 py-2 text-xs text-muted-foreground font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {scanResult.checks.map((c, i) => (
                  <tr key={i} className="border-b border-border/50 last:border-0">
                    <td className="px-3 py-2 text-foreground">{c.name}</td>
                    <td className={cn('px-3 py-2 font-mono font-bold', statusColor(c.status))}>
                      {statusIcon(c.status)}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground text-xs">{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="flex items-center justify-between pt-2 border-t border-border">
        <button
          onClick={() => setShowAudit(!showAudit)}
          className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <Activity className="h-4 w-4" />
          {showAudit ? 'Hide' : 'Show'} Audit Log ({auditEvents.length} events)
        </button>
      </div>

      {showAudit && auditEvents.length > 0 && (
        <div className="mt-3 rounded-lg border border-border overflow-hidden max-h-64 overflow-y-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-surface-800 sticky top-0">
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-32">Time</th>
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-24">Type</th>
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium w-20">User</th>
                <th className="text-left px-3 py-1.5 text-muted-foreground font-medium">Detail</th>
              </tr>
            </thead>
            <tbody>
              {auditEvents.map((e, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="px-3 py-1.5 text-muted-foreground font-mono">{e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : '—'}</td>
                  <td className="px-3 py-1.5">
                    <span className={cn(
                      'px-1.5 py-0.5 rounded text-[10px] font-medium',
                      e.event_type === 'security' ? 'bg-red-400/10 text-red-400' :
                      e.event_type === 'auth' ? 'bg-amber-400/10 text-amber-400' :
                      'bg-blue-400/10 text-blue-400'
                    )}>
                      {e.event_type}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-foreground">{e.user || '—'}</td>
                  <td className="px-3 py-1.5 text-muted-foreground truncate max-w-xs">{e.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAudit && auditEvents.length === 0 && (
        <p className="mt-3 text-xs text-muted-foreground text-center py-4">No audit events recorded yet</p>
      )}
    </div>
  )
}
