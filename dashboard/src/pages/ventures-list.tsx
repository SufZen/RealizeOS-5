import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertCircle, Plus, Trash2, Download, Info } from 'lucide-react'
import { TitleBlock } from '@/components/ui/title-block'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { useApi } from '@/hooks/use-api'
import { VentureHealthCard } from '@/components/venture-health-card'
import { CreateVentureModal } from '@/components/create-venture-modal'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Skeleton, SkeletonCard } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'
import { useAuth } from '@/hooks/use-auth'
import { useLocale } from '@/components/locale-provider'
import { ventureGates } from '@/lib/permissions'

interface VenturesResponse {
  ventures: Array<{
    key: string
    name: string
    description: string
    agent_count: number
    skill_count: number
    fabric_completeness: number
  }>
  /** False when realize-os.yaml is read-only; create and delete would fail. */
  config_writable?: boolean
}

export default function VenturesListPage() {
  const { data, loading, error, refetch } = useApi<VenturesResponse>('/ventures')
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)

  // Custom dialog state
  const [confirmDeleteKey, setConfirmDeleteKey] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const { user } = useAuth()
  const canEdit = data?.config_writable !== false
  // The role and venture scope decide too (the server checks again on every change).
  const { language } = useLocale()
  const gates = ventureGates(user, canEdit, language)

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
      setErrorMessage(null)
      refetch()
    } catch (err) {
      const detail = err instanceof ApiError || err instanceof Error ? err.message : ''
      setErrorMessage(detail ? `Failed to delete venture: ${detail}` : 'Failed to delete venture')
      refetch()
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
    <div className="mx-auto max-w-[1240px] space-y-6">
      <TitleBlock
        title="Ventures"
        description="Each venture is one business or project with its own agents, skills and company brain."
        actions={
          gates.canCreate && (
            <Button variant="primary" onClick={() => setShowCreate(true)}>
              <Plus aria-hidden />
              Create venture
            </Button>
          )
        }
      />

      {errorMessage && (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-[10px] border border-red-400/30 bg-red-400/10 p-3 text-sm text-red-400"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          {errorMessage}
        </div>
      )}

      {!canEdit && (
        <p className="m-0 flex items-start gap-2 rounded-[7px] border border-border bg-card px-3 py-2.5 text-[13px] text-muted-foreground">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" aria-hidden />
          <span>
            The server configuration is read-only here, so ventures can&apos;t be created or deleted
            from the dashboard. Change them in realize-os.yaml on the server.
          </span>
        </p>
      )}

      {gates.notice && (
        <p
          data-gate="ventures"
          className="m-0 flex items-start gap-2 rounded-[7px] border border-border bg-card px-3 py-2.5 text-[13px] text-muted-foreground"
        >
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" aria-hidden />
          <span>{gates.notice}</span>
        </p>
      )}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {data?.ventures.map((v) => (
          <div key={v.key} className="relative group">
            <VentureHealthCard
              name={v.name}
              ventureKey={v.key}
              agentCount={v.agent_count}
              skillCount={v.skill_count}
              onClick={() => navigate(`/ventures/${v.key}`, { viewTransition: true })}
            />
            {/* Action buttons overlay */}
            <div className="absolute top-3 end-3 flex gap-0.5 rounded-[7px] border border-border bg-card p-0.5 opacity-0 shadow-sm transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
              <button
                onClick={(e) => handleExport(v.key, e)}
                className="rz-icon-btn rz-icon-btn--sm"
                title="Export"
                aria-label={`Export ${v.key}`}
              >
                <Download className="h-3.5 w-3.5" />
              </button>
              {gates.canDelete && (
                <button
                  onClick={(e) => handleDeleteClick(v.key, e)}
                  disabled={deleting === v.key}
                  className="rz-icon-btn rz-icon-btn--sm hover:text-red-400"
                  title="Delete"
                  aria-label={`Delete ${v.key}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {data?.ventures.length === 0 && (
        <EmptyState
          art="documents"
          title="No ventures yet"
          body="Create a venture for each business or project. Its agents, skills and documents stay separate from the others."
          action={
            gates.canCreate && (
              <Button variant="primary" onClick={() => setShowCreate(true)}>
                <Plus aria-hidden />
                Create your first venture
              </Button>
            )
          }
        />
      )}

      <CreateVentureModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={refetch}
      />

      <ConfirmDialog
        isOpen={!!confirmDeleteKey}
        title="Delete venture?"
        message={`Delete venture "${confirmDeleteKey}"? This removes all FABRIC files and cannot be undone.`}
        isDestructive={true}
        confirmText={deleting ? 'Deleting...' : 'Delete venture'}
        onConfirm={executeDelete}
        onCancel={() => setConfirmDeleteKey(null)}
      />
    </div>
  )
}
