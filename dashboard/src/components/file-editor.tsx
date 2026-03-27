import { useState, useEffect } from 'react'
import { Save, X, AlertCircle, Check, Trash2 } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

interface Props {
  ventureKey: string
  filePath: string
  initialContent: string
  onClose: () => void
  onSaved: () => void
  onDeleted?: () => void
}

export function FileEditor({ ventureKey, filePath, initialContent, onClose, onSaved, onDeleted }: Props) {
  const [content, setContent] = useState(initialContent)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ msg: string; type: 'success' | 'error' } | null>(null)
  const [showConfirmDelete, setShowConfirmDelete] = useState(false)
  const isDirty = content !== initialContent
  const isYaml = filePath.endsWith('.yaml') || filePath.endsWith('.yml')

  useEffect(() => {
    setContent(initialContent)
    setStatus(null)
  }, [initialContent, filePath])

  async function handleSave() {
    setSaving(true)
    setStatus(null)
    try {
      await api.put(`/ventures/${ventureKey}/kb/file`, { path: filePath, content })
      setStatus({ msg: 'Saved', type: 'success' })
      onSaved()
    } catch (err) {
      setStatus({ msg: err instanceof Error ? err.message : 'Save failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete() {
    setShowConfirmDelete(false)
    setSaving(true)
    try {
      await api.delete(`/ventures/${ventureKey}/kb/file?path=${encodeURIComponent(filePath)}`)
      onDeleted?.()
      onClose()
    } catch (err) {
      setStatus({ msg: err instanceof Error ? err.message : 'Delete failed', type: 'error' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 pb-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-mono text-muted-foreground truncate">{filePath}</span>
          {isYaml && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400 shrink-0">YAML</span>
          )}
          {isDirty && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-brand-400/10 text-brand-400 shrink-0">Modified</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {status && (
            <span className={cn(
              'flex items-center gap-1 text-xs',
              status.type === 'success' ? 'text-green-400' : 'text-red-400',
            )}>
              {status.type === 'success' ? <Check className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
              {status.msg}
            </span>
          )}
          {onDeleted && (
            <button
              onClick={() => setShowConfirmDelete(true)}
              disabled={saving}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-red-400 transition-colors"
              title="Delete file"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving || !isDirty}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg font-medium transition-colors',
              'bg-brand-400 text-black hover:bg-brand-400/90',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            )}
          >
            <Save className="h-3.5 w-3.5" />
            {saving ? 'Saving...' : 'Save'}
          </button>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Editor */}
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        spellCheck={false}
        className={cn(
          'flex-1 w-full mt-3 rounded-lg border border-border bg-surface-800 p-4',
          'text-sm text-foreground font-mono leading-relaxed resize-none',
          'focus:outline-none focus:ring-1 focus:ring-brand-400',
        )}
      />
      <ConfirmDialog
        isOpen={showConfirmDelete}
        title="Delete File"
        message={`Delete ${filePath.split('/').pop()}? This cannot be undone.`}
        isDestructive={true}
        confirmText="Delete"
        onConfirm={handleDelete}
        onCancel={() => setShowConfirmDelete(false)}
      />
    </div>
  )
}

interface CreateFileProps {
  ventureKey: string
  directory: string
  extension: '.md' | '.yaml'
  onCreated: () => void
  onCancel: () => void
}

export function CreateFileDialog({ ventureKey, directory, extension, onCreated, onCancel }: CreateFileProps) {
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleCreate() {
    if (!name.trim()) return
    const fileName = name.trim().endsWith(extension) ? name.trim() : `${name.trim()}${extension}`
    const path = `${directory}/${fileName}`

    setSaving(true)
    setError('')
    try {
      const defaultContent = extension === '.yaml'
        ? `name: ${name.replace(extension, '')}\ntriggers:\n  - example\ntask_type: general\nsteps:\n  - type: agent\n    agent: orchestrator\n    prompt: "Execute the task"\n`
        : `# ${name.replace(extension, '')}\n\nDescribe this ${directory.includes('A-agents') ? 'agent' : 'document'} here.\n`

      await api.post(`/ventures/${ventureKey}/kb/file`, { path, content: defaultContent })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center gap-2 p-2 bg-surface-800 rounded-lg border border-brand-400/30">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
        placeholder={`filename${extension}`}
        autoFocus
        className="flex-1 bg-transparent text-sm text-foreground px-2 py-1 focus:outline-none"
      />
      <button
        onClick={handleCreate}
        disabled={saving || !name.trim()}
        className="px-3 py-1 text-xs rounded bg-brand-400 text-black font-medium disabled:opacity-40"
      >
        Create
      </button>
      <button onClick={onCancel} className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground">
        Cancel
      </button>
      {error && <span className="text-xs text-red-400">{error}</span>}
    </div>
  )
}
