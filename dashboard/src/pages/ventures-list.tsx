import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Briefcase, AlertCircle, Plus, Trash2, Download } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { VentureHealthCard } from '@/components/venture-health-card'
import { CreateVentureModal } from '@/components/create-venture-modal'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Skeleton, SkeletonCard } from '@/components/ui/skeleton'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface VenturesResponse {
  ventures: Array<{
    key: string
    name: string
    description: string
    agent_count: number
    skill_count: number
    fabric_completeness: number
  }>
}

export default function VenturesListPage() {
  const { data, loading, error, refetch } = useApi<VenturesResponse>('/ventures')
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  
  // Custom dialog state
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  function handleDeleteClick(key: string, e: React.MouseEvent) {
    e.stopPropagation()
    setConfirmDeleteKey(key)
  }

  async function executeDelete() {
    if (!confirmDeleteKey) return
    const key = confirmDeleteKey
    setConfirmDeleteKey(null)
    setDeleting(key)
    try {
      await api.delete(`/ventures/${key}`)
      refetch()
    } catch {
      setErrorMessage('Failed to delete venture')
    } finally {
      setDeleting(null)
    }
  }

  function handleExport(key: string, e: React.MouseEvent) {
    e.stopPropagation()
    window.open(`/api/ventures/${key}/export`, '_blank')
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Skeleton className="h-6 w-6 rounded-full bg-brand-400/20" />
            <Skeleton className="h-8 w-32" />
          </div>
          <Skeleton className="h-9 w-32 rounded-lg" />
        </div>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-64">
        <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
        <p className="text-red-400 text-sm">{error}</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {errorMessage && (
        <div className="bg-red-500/10 text-red-400 p-3 rounded-lg flex items-center gap-2 text-sm border border-red-500/20">
          <AlertCircle className="h-4 w-4" />
          {errorMessage}
        </div>
      )}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Briefcase className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Ventures</h1>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className={cn(
            'flex items-center gap-2 px-4 py-2 text-sm rounded-lg font-medium transition-colors',
            'bg-brand-400 text-black hover:bg-brand-400/90',
          )}
        >
          <Plus className="h-4 w-4" />
          Create Venture
        </button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data?.ventures.map((v) => (
          <div key={v.key} className="relative group">
            <VentureHealthCard
              name={v.name}
              ventureKey={v.key}
              agentCount={v.agent_count}
              skillCount={v.skill_count}
              onClick={() => navigate(`/ventures/${v.key}`)}
            />
            {/* Action buttons overlay */}
            <div className="absolute top-3 right-3 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={(e) => handleExport(v.key, e)}
                className="p-1.5 rounded-lg bg-surface-800/80 border border-border text-muted-foreground hover:text-foreground transition-colors"
                title="Export"
                aria-label={`Export ${v.key}`}
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={(e) => handleDeleteClick(v.key, e)}
                disabled={deleting === v.key}
                className="p-1.5 rounded-lg bg-surface-800/80 border border-border text-muted-foreground hover:text-red-400 transition-colors"
                title="Delete"
                aria-label={`Delete ${v.key}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {data?.ventures.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Briefcase className="h-12 w-12 text-muted-foreground/30 mb-4" />
          <p className="text-muted-foreground text-sm mb-4">No ventures configured yet.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 font-medium transition-colors"
          >
            <Plus className="h-4 w-4" />
            Create your first venture
          </button>
        </div>
      )}

      <CreateVentureModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={refetch}
      />

      <ConfirmDialog
        isOpen={!!confirmDeleteKey}
        title="Delete Venture"
        message={`Delete venture "${confirmDeleteKey}"? This removes all FABRIC files and cannot be undone.`}
        isDestructive={true}
        confirmText={deleting ? "Deleting..." : "Delete Venture"}
        onConfirm={executeDelete}
        onCancel={() => setConfirmDeleteKey(null)}
      />
    </div>
  )
}
