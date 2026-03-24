import { useState, useEffect } from 'react'
import { Cloud, RefreshCw, Check, Loader2, TestTube2, Download } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Toggle, StatusBanner } from './shared'

const S3_PROVIDERS = [
  { label: 'AWS S3', value: '', hint: 'Leave endpoint empty for standard AWS S3' },
  { label: 'MinIO (Self-Hosted)', value: 'http://localhost:9000', hint: 'Your MinIO server URL' },
  { label: 'DigitalOcean Spaces', value: 'https://{region}.digitaloceanspaces.com', hint: 'e.g. nyc3, sfo3, sgp1' },
  { label: 'Backblaze B2', value: 'https://s3.{region}.backblazeb2.com', hint: 'e.g. us-west-004' },
  { label: 'Cloudflare R2', value: 'https://{account_id}.r2.cloudflarestorage.com', hint: 'Your CF account ID' },
  { label: 'Custom S3-Compatible', value: '', hint: 'Enter your endpoint URL' },
]

export function StorageSection() {
  const [provider, setProvider] = useState('local')
  const [bucket, setBucket] = useState('')
  const [region, setRegion] = useState('us-east-1')
  const [accessKey, setAccessKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [endpointUrl, setEndpointUrl] = useState('')
  const [syncEnabled, setSyncEnabled] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [storageStatus, setStorageStatus] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [stats, setStats] = useState<{ ventures: number; total_size_bytes: number } | null>(null)

  useEffect(() => {
    api.get<{ config: Record<string, string | boolean>; stats: { ventures: number; total_size_bytes: number } }>('/storage/config')
      .then(res => {
        const cfg = res.config
        setProvider((cfg.provider as string) || 'local')
        setBucket((cfg.s3_bucket as string) || '')
        setRegion((cfg.s3_region as string) || 'us-east-1')
        setEndpointUrl((cfg.s3_endpoint_url as string) || '')
        setSyncEnabled(!!(cfg.sync_enabled))
        setStats(res.stats)
      })
      .catch(() => {})
  }, [])

  async function handleTestConnection() {
    setTesting(true)
    setStorageStatus(null)
    try {
      const res = await api.post<{ message: string }>('/storage/test', {
        provider, s3_bucket: bucket, s3_region: region,
        s3_access_key: accessKey, s3_secret_key: secretKey,
        s3_endpoint_url: endpointUrl, sync_enabled: syncEnabled,
      })
      setStorageStatus({ message: res.message, type: 'success' })
    } catch (e: unknown) {
      setStorageStatus({ message: (e as Error).message || 'Connection test failed', type: 'error' })
    } finally {
      setTesting(false)
    }
  }

  async function handleSave() {
    setSaving(true)
    setStorageStatus(null)
    try {
      await api.put('/storage/config', {
        provider, s3_bucket: bucket, s3_region: region,
        s3_access_key: accessKey, s3_secret_key: secretKey,
        s3_endpoint_url: endpointUrl, sync_enabled: syncEnabled,
      })
      setStorageStatus({ message: 'Storage configuration saved.', type: 'success' })
    } catch {
      setStorageStatus({ message: 'Failed to save config', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function handleExport() {
    setExporting(true)
    try {
      const res = await api.post<{ message: string; path: string }>('/storage/export')
      setStorageStatus({ message: `${res.message} → ${res.path}`, type: 'success' })
    } catch {
      setStorageStatus({ message: 'Export failed', type: 'error' })
    } finally {
      setExporting(false)
    }
  }

  const inputClass = 'w-full bg-surface-800 border border-border rounded-lg px-3 py-2 text-sm text-foreground placeholder-muted-foreground outline-none focus:border-brand-400'

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Cloud className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Storage & Backup</h2>
      </div>

      {stats && (
        <p className="text-xs text-muted-foreground mb-4">
          {stats.ventures} venture(s) · {(stats.total_size_bytes / 1024 / 1024).toFixed(1)} MB on disk
        </p>
      )}

      {storageStatus && <StatusBanner message={storageStatus.message} type={storageStatus.type} />}

      <div className="space-y-4 mt-4">
        <div className="flex items-center justify-between">
          <span className="text-sm text-foreground">Storage backend</span>
          <div className="flex gap-2">
            <button
              onClick={() => setProvider('local')}
              className={cn('px-3 py-1 text-xs rounded-lg border transition-colors',
                provider === 'local'
                  ? 'bg-brand-400/10 text-brand-400 border-brand-400/30'
                  : 'border-border text-muted-foreground hover:text-foreground'
              )}
            >Local</button>
            <button
              onClick={() => setProvider('s3')}
              className={cn('px-3 py-1 text-xs rounded-lg border transition-colors',
                provider === 's3'
                  ? 'bg-brand-400/10 text-brand-400 border-brand-400/30'
                  : 'border-border text-muted-foreground hover:text-foreground'
              )}
            >S3 Cloud</button>
          </div>
        </div>

        {provider === 's3' && (
          <div className="space-y-3 pl-2 border-l-2 border-brand-400/20">
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Provider Template</label>
              <select
                onChange={(e) => {
                  const p = S3_PROVIDERS.find(p => p.label === e.target.value)
                  if (p) setEndpointUrl(p.value)
                }}
                className={inputClass}
              >
                {S3_PROVIDERS.map(p => (
                  <option key={p.label} value={p.label}>{p.label} — {p.hint}</option>
                ))}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Bucket</label>
                <input value={bucket} onChange={e => setBucket(e.target.value)} placeholder="my-realizeos-bucket" className={inputClass} />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Region</label>
                <input value={region} onChange={e => setRegion(e.target.value)} placeholder="us-east-1" className={inputClass} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Access Key</label>
                <input value={accessKey} onChange={e => setAccessKey(e.target.value)} type="password" placeholder="AKIA..." className={inputClass} />
              </div>
              <div>
                <label className="text-xs text-muted-foreground mb-1 block">Secret Key</label>
                <input value={secretKey} onChange={e => setSecretKey(e.target.value)} type="password" placeholder="••••••••" className={inputClass} />
              </div>
            </div>
            <div>
              <label className="text-xs text-muted-foreground mb-1 block">Endpoint URL (custom/non-AWS)</label>
              <input value={endpointUrl} onChange={e => setEndpointUrl(e.target.value)} placeholder="https://..." className={inputClass} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-foreground">Auto-sync enabled</span>
              <Toggle checked={syncEnabled} onChange={setSyncEnabled} />
            </div>
          </div>
        )}

        {syncEnabled && <SyncStatusPanel />}

        <div className="flex gap-3 pt-2">
          {provider === 's3' && (
            <button
              onClick={handleTestConnection}
              disabled={testing || !bucket}
              className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
            >
              {testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube2 className="h-4 w-4" />}
              Test Connection
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-brand-400 text-black font-medium hover:bg-brand-300 disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
            Save Config
          </button>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-border bg-surface-800 text-foreground hover:bg-surface-700 disabled:opacity-50 transition-colors"
          >
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            Export All Data
          </button>
        </div>
      </div>
    </div>
  )
}

function SyncStatusPanel() {
  const [syncInfo, setSyncInfo] = useState<{
    sync_enabled: boolean; is_running: boolean;
    last_sync: { completed_at: string; sync_type: string } | null;
    stats: Record<string, number>
  } | null>(null)
  const [syncing, setSyncing] = useState(false)

  useEffect(() => {
    api.get<typeof syncInfo>('/storage/sync/status')
      .then(res => setSyncInfo(res))
      .catch(() => {})
  }, [syncing])

  async function triggerSync() {
    setSyncing(true)
    try {
      await api.post('/storage/sync/trigger')
    } catch {
      // handled by status refresh
    } finally {
      setTimeout(() => setSyncing(false), 3000)
    }
  }

  if (!syncInfo) return null

  return (
    <div className="rounded-lg bg-surface-800 p-4 border border-border/50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-foreground flex items-center gap-2">
          <RefreshCw className={cn('h-4 w-4', syncInfo.is_running && 'animate-spin text-brand-400')} />
          Sync Status
        </span>
        <button
          onClick={triggerSync}
          disabled={syncing || syncInfo.is_running}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border bg-surface-700 text-foreground hover:bg-surface-600 disabled:opacity-50 transition-colors"
        >
          {(syncing || syncInfo.is_running)
            ? <><Loader2 className="h-3 w-3 animate-spin" /> Syncing...</>
            : <><RefreshCw className="h-3 w-3" /> Sync Now</>
          }
        </button>
      </div>
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <span className="text-muted-foreground">Status</span>
          <p className={cn('font-medium', syncInfo.is_running ? 'text-brand-400' : 'text-emerald-400')}>
            {syncInfo.is_running ? 'Running' : 'Idle'}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Last Sync</span>
          <p className="text-foreground">
            {syncInfo.last_sync?.completed_at
              ? new Date(syncInfo.last_sync.completed_at).toLocaleString()
              : 'Never'}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground">Operations</span>
          <p className="text-foreground">
            {Object.entries(syncInfo.stats || {}).map(([k, v]) => `${k}: ${v}`).join(', ') || 'None'}
          </p>
        </div>
      </div>
    </div>
  )
}
