import { useState } from 'react'
import { BookOpen, Download, Check, AlertCircle, Loader2, Zap } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

interface SkillTemplate {
  id: string
  name: string
  description: string
  category: string
  task_type?: string
  triggers?: string[]
  steps?: number
}

interface LibraryData {
  skills: SkillTemplate[]
  categories: string[]
}

interface VenturesData {
  ventures: Array<{ key: string; name: string }>
}

export default function SkillsPage() {
  const { data, loading, error } = useApi<LibraryData>('/skills/library')
  const { data: venturesData } = useApi<VenturesData>('/ventures')
  const [filter, setFilter] = useState('')
  const [installing, setInstalling] = useState<string | null>(null)
  const [installed, setInstalled] = useState<Set<string>>(new Set())
  const [selectedVenture, setSelectedVenture] = useState('')
  const [installError, setInstallError] = useState<string | null>(null)

  async function handleInstall(skillId: string) {
    if (!selectedVenture) {
      setInstallError('Select a venture first')
      return
    }
    setInstalling(skillId)
    setInstallError(null)
    try {
      await api.post('/skills/install', { skill_id: skillId, venture_key: selectedVenture })
      setInstalled((prev) => new Set(prev).add(skillId))
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : 'Install failed')
    } finally {
      setInstalling(null)
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading skill library...</div>
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load skill library
      </div>
    )
  }

  const filtered = filter
    ? data.skills.filter((s) => s.category === filter)
    : data.skills

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-2">
        <BookOpen className="h-6 w-6 text-brand-400" />
        <h1 className="text-2xl font-bold text-foreground">Skill Library</h1>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap gap-3 items-center">
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('')}
            className={cn(
              'px-3 py-1.5 text-xs rounded-lg border transition-colors',
              !filter ? 'border-brand-400 text-brand-400 bg-brand-400/10' : 'border-border text-muted-foreground hover:text-foreground',
            )}
          >
            All ({data.skills.length})
          </button>
          {data.categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setFilter(cat)}
              className={cn(
                'px-3 py-1.5 text-xs rounded-lg border transition-colors capitalize',
                filter === cat ? 'border-brand-400 text-brand-400 bg-brand-400/10' : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              {cat}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Install to:</span>
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

      {installError && (
        <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
          <AlertCircle className="h-4 w-4" />
          {installError}
        </div>
      )}

      {/* Skill Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        {filtered.map((skill) => (
          <div key={skill.id} className="rounded-xl border border-border bg-card p-5">
            <div className="flex items-start justify-between mb-2">
              <div>
                <h3 className="text-sm font-semibold text-foreground">{skill.name}</h3>
                <span className="text-xs text-muted-foreground capitalize">{skill.category}</span>
              </div>
              {installed.has(skill.id) ? (
                <span className="flex items-center gap-1 text-xs text-green-400 px-2 py-1 rounded-lg bg-green-400/10">
                  <Check className="h-3.5 w-3.5" />
                  Installed
                </span>
              ) : (
                <button
                  onClick={() => handleInstall(skill.id)}
                  disabled={installing === skill.id || !selectedVenture}
                  className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40 transition-colors font-medium"
                >
                  {installing === skill.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                  Install
                </button>
              )}
            </div>

            <p className="text-xs text-muted-foreground mb-3">{skill.description}</p>

            <div className="flex flex-wrap gap-2">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-700 text-muted-foreground">
                {skill.task_type || 'general'}
              </span>
              {(skill.steps ?? 0) > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-700 text-muted-foreground">
                  {skill.steps} step{skill.steps !== 1 ? 's' : ''}
                </span>
              )}
              {(skill.triggers ?? []).slice(0, 3).map((t) => (
                <span key={t} className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded bg-brand-400/10 text-brand-400">
                  <Zap className="h-2.5 w-2.5" />
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {filtered.length === 0 && (
        <div className="text-center py-12 text-muted-foreground text-sm">
          No skills found in this category.
        </div>
      )}
    </div>
  )
}
