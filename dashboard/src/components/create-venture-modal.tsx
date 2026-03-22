import { useState } from 'react'
import { X, Plus } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

export function CreateVentureModal({ open, onClose, onCreated }: Props) {
  const [key, setKey] = useState('')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  if (!open) return null

  async function handleCreate() {
    if (!key.trim()) {
      setError('Venture key is required')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.post('/ventures', { key: key.trim(), name: name.trim(), description: description.trim() })
      setKey('')
      setName('')
      setDescription('')
      onCreated()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create venture')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md rounded-xl border border-border bg-surface-950 p-6 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">Create Venture</h2>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm text-muted-foreground mb-1">Key (identifier)</label>
              <input
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="my-venture"
                className="w-full rounded-lg border border-border bg-surface-800 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
              />
            </div>
            <div>
              <label className="block text-sm text-muted-foreground mb-1">Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="My Venture"
                className="w-full rounded-lg border border-border bg-surface-800 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
              />
            </div>
            <div>
              <label className="block text-sm text-muted-foreground mb-1">Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What does this venture do?"
                rows={2}
                className="w-full rounded-lg border border-border bg-surface-800 px-3 py-2 text-sm text-foreground resize-none focus:outline-none focus:ring-1 focus:ring-brand-400"
              />
            </div>

            {error && (
              <p className="text-sm text-red-400">{error}</p>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm rounded-lg border border-border text-muted-foreground hover:text-foreground transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={saving || !key.trim()}
                className={cn(
                  'flex items-center gap-2 px-4 py-2 text-sm rounded-lg font-medium transition-colors',
                  'bg-brand-400 text-black hover:bg-brand-400/90',
                  'disabled:opacity-40 disabled:cursor-not-allowed',
                )}
              >
                <Plus className="h-4 w-4" />
                {saving ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
