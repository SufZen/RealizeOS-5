import { useState } from 'react'
import { AlertCircle } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { StatusBanner } from './settings/shared'
import { SecuritySection } from './settings/settings-security'
import { StorageSection } from './settings/settings-storage'
import { HelpSection, DevModeSection } from './settings/settings-devmode'

import { 
  FeatureFlagsSection, 
  GovernanceGatesSection, 
  LLMProvidersSection, 
  SystemInfoSection, 
  MaintenanceSection 
} from './settings/settings-core'

import { 
  LLMRoutingSection, 
  MemorySection, 
  ReportsSection, 
  TrustLadderSection 
} from './settings/settings-advanced'

interface Provider {
  name: string
  available: boolean
  models: string[]
}

interface SettingsData {
  features: Record<string, boolean>
  gates: Record<string, boolean>
  providers: Provider[]
  system_info: {
    python_version: string
    db_size_bytes: number
    kb_file_count: number
    config_path: string
  }
}

export default function SettingsPage() {
  const { data, loading, error, refetch } = useApi<SettingsData>('/settings')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ message: string; type: 'success' | 'error' } | null>(null)

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading settings...</div>
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load settings
      </div>
    )
  }

  async function toggleFeature(key: string, value: boolean) {
    setSaving(true)
    setStatus(null)
    try {
      await api.put('/settings/features', { [key]: value })
      setStatus({ message: `Feature "${key}" ${value ? 'enabled' : 'disabled'}`, type: 'success' })
      refetch()
    } catch {
      setStatus({ message: `Failed to update feature "${key}"`, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function toggleGate(key: string, value: boolean) {
    setSaving(true)
    setStatus(null)
    try {
      await api.put('/settings/gates', { [key]: value })
      setStatus({ message: `Gate "${key}" ${value ? 'enabled' : 'disabled'}`, type: 'success' })
      refetch()
    } catch {
      setStatus({ message: `Failed to update gate "${key}"`, type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function handleReindex() {
    setSaving(true)
    setStatus(null)
    try {
      const res = await api.post<{ files_indexed: number }>('/settings/reindex')
      setStatus({ message: `KB re-indexed: ${res.files_indexed} files`, type: 'success' })
      refetch()
    } catch {
      setStatus({ message: 'Re-index failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function handleReload() {
    setSaving(true)
    setStatus(null)
    try {
      await api.post('/systems/reload')
      setStatus({ message: 'Configuration reloaded', type: 'success' })
      refetch()
    } catch {
      setStatus({ message: 'Reload failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold text-foreground">Settings</h1>

      {status && <StatusBanner message={status.message} type={status.type} />}

      <FeatureFlagsSection features={data.features} saving={saving} onToggle={toggleFeature} />
      <GovernanceGatesSection gates={data.gates} saving={saving} onToggle={toggleGate} />
      <LLMProvidersSection providers={data.providers} />
      <SystemInfoSection info={data.system_info} />
      
      <MaintenanceSection 
        saving={saving} 
        onReload={handleReload} 
        onReindex={handleReindex} 
      />

      <ReportsSection saving={saving} setSaving={setSaving} setStatus={setStatus} />
      <TrustLadderSection />
      <SecuritySection saving={saving} setSaving={setSaving} setStatus={setStatus} />
      <LLMRoutingSection />
      <MemorySection />
      <StorageSection />
      <HelpSection />
      <DevModeSection />
    </div>
  )
}
