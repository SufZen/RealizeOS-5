import { useState, useCallback, useMemo } from 'react'
import { useDebounce } from '@/hooks/use-debounce'
import {
  FileCode2,
  Plus,
  Save,
  Eye,
  Code2,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Copy,
  FileText,
  Search,
  Zap,
  Tag,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type EditorFormat = 'yaml' | 'skill_md'
type EditorView = 'code' | 'preview'

interface WorkflowFile {
  id: string
  name: string
  format: EditorFormat
  content: string
  venture_key: string
  updated_at?: string
}

interface WorkflowsData {
  workflows: WorkflowFile[]
}

interface VenturesData {
  ventures: Array<{ key: string; name: string }>
}

/* ------------------------------------------------------------------ */
/* SKILL.md template                                                   */
/* ------------------------------------------------------------------ */

const SKILL_MD_TEMPLATE = `---
name: new_skill
description: A brief description of what this skill does
triggers:
  - trigger phrase one
  - trigger phrase two
tags: [general]
agent: orchestrator
---

# Skill Title

Detailed instructions for the LLM agent executing this skill.

## Context
Explain the context and purpose of this skill.

## Steps
1. First step
2. Second step
3. Third step

## Output Format
Describe the expected output.
`

const YAML_TEMPLATE = `name: new_pipeline
triggers:
  - trigger phrase
task_type: general
steps:
  - id: step1
    type: agent
    agent: orchestrator
    prompt: "Analyze the following request: {user_message}"
  - id: step2
    type: agent
    agent: reviewer
    inject_context: [step1]
    prompt: "Review the analysis and suggest improvements."
`

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

export default function WorkflowEditorPage() {
  const { data, loading, error } = useApi<WorkflowsData>('/workflows')
  const { data: venturesData } = useApi<VenturesData>('/ventures')
  const [selectedVenture, setSelectedVenture] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Editor state
  const [format, setFormat] = useState<EditorFormat>('skill_md')
  const [view, setView] = useState<EditorView>('code')
  const [content, setContent] = useState(SKILL_MD_TEMPLATE)
  const [filename, setFilename] = useState('new_skill')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [activeFileId, setActiveFileId] = useState<string | null>(null)

  /* ---- Format switch ---- */
  const handleFormatSwitch = useCallback((newFormat: EditorFormat) => {
    setFormat(newFormat)
    if (!activeFileId) {
      setContent(newFormat === 'skill_md' ? SKILL_MD_TEMPLATE : YAML_TEMPLATE)
      setFilename(newFormat === 'skill_md' ? 'new_skill' : 'new_pipeline')
    }
  }, [activeFileId])

  /* ---- New file ---- */
  const handleNew = useCallback(() => {
    setActiveFileId(null)
    setContent(format === 'skill_md' ? SKILL_MD_TEMPLATE : YAML_TEMPLATE)
    setFilename(format === 'skill_md' ? 'new_skill' : 'new_pipeline')
    setSaveStatus('idle')
  }, [format])

  /* ---- Load file ---- */
  const handleLoad = useCallback((file: WorkflowFile) => {
    setActiveFileId(file.id)
    setFormat(file.format)
    setContent(file.content)
    setFilename(file.name)
    setSelectedVenture(file.venture_key)
    setView('code')
    setSaveStatus('idle')
  }, [])

  /* ---- Save ---- */
  const handleSave = useCallback(async () => {
    if (!selectedVenture) return
    setSaveStatus('saving')
    try {
      await api.post('/workflows', {
        id: activeFileId,
        name: filename,
        format,
        content,
        venture_key: selectedVenture,
      })
      setSaveStatus('saved')
      setTimeout(() => setSaveStatus('idle'), 2000)
    } catch {
      setSaveStatus('error')
    }
  }, [activeFileId, filename, format, content, selectedVenture])

  /* ---- Copy ---- */
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(content)
  }, [content])

  /* ---- Filtered files ---- */
  const debouncedSearch = useDebounce(searchQuery, 250)
  const filteredFiles = useMemo(() => {
    if (!data?.workflows) return []
    let files = data.workflows
    if (selectedVenture) {
      files = files.filter((f) => f.venture_key === selectedVenture)
    }
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase()
      files = files.filter(
        (f) => f.name.toLowerCase().includes(q) || f.content.toLowerCase().includes(q),
      )
    }
    return files
  }, [data, selectedVenture, debouncedSearch])

  /* ---- Preview parsing ---- */
  const preview = useMemo(() => {
    if (format === 'skill_md') {
      return parseSkillMdPreview(content)
    }
    return parseYamlPreview(content)
  }, [content, format])

  return (
    <div className="space-y-6 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileCode2 className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Workflow Editor</h1>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedVenture}
            onChange={(e) => setSelectedVenture(e.target.value)}
            className="appearance-none bg-surface-800 border border-border rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
          >
            <option value="">All ventures</option>
            {venturesData?.ventures.map((v) => (
              <option key={v.key} value={v.key}>{v.name || v.key}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[280px,1fr]">
        {/* Sidebar — file browser */}
        <div className="rounded-xl border border-border bg-card p-4 space-y-4">
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search files..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-border bg-surface-800 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
              />
            </div>
            <button
              onClick={handleNew}
              className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-brand-400 hover:border-brand-400/50 transition-colors"
              title="New file"
              aria-label="Create new file"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>

          {loading ? (
            <div className="text-xs text-muted-foreground text-center py-8">Loading...</div>
          ) : error ? (
            <div className="text-xs text-red-400 text-center py-8">Failed to load</div>
          ) : filteredFiles.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-8">
              No workflow files found
            </div>
          ) : (
            <div className="space-y-1 max-h-[60vh] overflow-y-auto">
              {filteredFiles.map((file) => (
                <button
                  key={file.id}
                  onClick={() => handleLoad(file)}
                  className={cn(
                    'w-full text-left rounded-lg px-3 py-2 text-xs transition-colors',
                    activeFileId === file.id
                      ? 'bg-brand-400/10 text-brand-400'
                      : 'text-muted-foreground hover:bg-surface-700 hover:text-foreground',
                  )}
                >
                  <div className="flex items-center gap-2">
                    <FileText className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate font-medium">{file.name}</span>
                    <span className={cn(
                      'ml-auto text-[9px] px-1 py-0.5 rounded uppercase tracking-wider shrink-0',
                      file.format === 'skill_md'
                        ? 'bg-purple-400/10 text-purple-400'
                        : 'bg-cyan-400/10 text-cyan-400',
                    )}>
                      {file.format === 'skill_md' ? 'MD' : 'YAML'}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Editor pane */}
        <div className="space-y-4">
          {/* Editor toolbar */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Format toggle */}
            <div className="flex rounded-lg border border-border overflow-hidden">
              {(['skill_md', 'yaml'] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => handleFormatSwitch(f)}
                  className={cn(
                    'px-3 py-1.5 text-xs font-medium transition-colors',
                    format === f
                      ? 'bg-brand-400/10 text-brand-400'
                      : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {f === 'skill_md' ? 'SKILL.md' : 'YAML'}
                </button>
              ))}
            </div>

            {/* View toggle */}
            <div className="flex rounded-lg border border-border overflow-hidden">
              <button
                onClick={() => setView('code')}
                className={cn(
                  'flex items-center gap-1 px-3 py-1.5 text-xs transition-colors',
                  view === 'code'
                    ? 'bg-brand-400/10 text-brand-400'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <Code2 className="h-3 w-3" /> Code
              </button>
              <button
                onClick={() => setView('preview')}
                className={cn(
                  'flex items-center gap-1 px-3 py-1.5 text-xs transition-colors',
                  view === 'preview'
                    ? 'bg-brand-400/10 text-brand-400'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <Eye className="h-3 w-3" /> Preview
              </button>
            </div>

            {/* Filename */}
            <input
              value={filename}
              onChange={(e) => setFilename(e.target.value)}
              className="rounded-lg border border-border bg-surface-800 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400 font-mono w-40"
              placeholder="filename"
            />

            {/* Actions */}
            <div className="ml-auto flex items-center gap-2">
              <button
                onClick={handleCopy}
                className="p-1.5 rounded-lg border border-border text-muted-foreground hover:text-foreground transition-colors"
                title="Copy"
                aria-label="Copy to clipboard"
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={handleSave}
                disabled={!selectedVenture || saveStatus === 'saving'}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg font-medium transition-colors',
                  saveStatus === 'saved'
                    ? 'bg-green-400/10 text-green-400 border border-green-400/20'
                    : 'bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40',
                )}
              >
                {saveStatus === 'saving' ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : saveStatus === 'saved' ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                {saveStatus === 'saved' ? 'Saved' : 'Save'}
              </button>
            </div>
          </div>

          {/* Editor body */}
          {view === 'code' ? (
            <div className="rounded-xl border border-border bg-surface-900 overflow-hidden">
              {/* Line numbers + editor */}
              <div className="relative">
                <textarea
                  value={content}
                  onChange={(e) => setContent(e.target.value)}
                  spellCheck={false}
                  className={cn(
                    'w-full min-h-[500px] bg-transparent text-xs text-foreground font-mono',
                    'p-4 pl-14 leading-6 resize-y',
                    'focus:outline-none focus:ring-0 border-none',
                  )}
                />
                {/* Line numbers overlay */}
                <div className="absolute left-0 top-0 w-10 p-4 text-right pointer-events-none select-none">
                  {content.split('\n').map((_, i) => (
                    <div key={i} className="text-[10px] leading-6 text-surface-600 font-mono">
                      {i + 1}
                    </div>
                  ))}
                </div>
              </div>

              {/* Status bar */}
              <div className="flex items-center justify-between px-4 py-1.5 border-t border-border text-[10px] text-muted-foreground">
                <span>{format === 'skill_md' ? 'Markdown + YAML Frontmatter' : 'YAML'}</span>
                <span>{content.split('\n').length} lines</span>
              </div>
            </div>
          ) : (
            /* Preview pane */
            <div className="rounded-xl border border-border bg-card p-6 min-h-[500px]">
              {preview ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2">
                    <h2 className="text-lg font-semibold text-foreground">{preview.name}</h2>
                    <span className={cn(
                      'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider',
                      format === 'skill_md'
                        ? 'bg-purple-400/10 text-purple-400'
                        : 'bg-cyan-400/10 text-cyan-400',
                    )}>
                      {format === 'skill_md' ? 'SKILL.MD' : 'YAML'}
                    </span>
                  </div>

                  {preview.description && (
                    <p className="text-sm text-muted-foreground">{preview.description}</p>
                  )}

                  {preview.triggers.length > 0 && (
                    <div>
                      <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Triggers</h3>
                      <div className="flex flex-wrap gap-1.5">
                        {preview.triggers.map((t: string) => (
                          <span key={t} className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg bg-brand-400/10 text-brand-400 border border-brand-400/20">
                            <Zap className="h-2.5 w-2.5" /> {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {preview.tags.length > 0 && (
                    <div>
                      <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Tags</h3>
                      <div className="flex flex-wrap gap-1.5">
                        {preview.tags.map((t: string) => (
                          <span key={t} className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-lg bg-surface-700 text-muted-foreground">
                            <Tag className="h-2.5 w-2.5" /> {t}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {preview.body && (
                    <div>
                      <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2">Instructions</h3>
                      <div className="prose prose-invert prose-sm max-w-none">
                        <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono bg-surface-900 rounded-lg p-4">
                          {preview.body}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-64 text-muted-foreground gap-2">
                  <AlertCircle className="h-8 w-8 opacity-30" />
                  <p className="text-sm">Could not parse content</p>
                  <p className="text-xs">Check your YAML frontmatter syntax</p>
                </div>
              )}
            </div>
          )}

          {saveStatus === 'error' && (
            <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2">
              <AlertCircle className="h-4 w-4" />
              Failed to save workflow
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Preview parsers                                                     */
/* ------------------------------------------------------------------ */

interface PreviewData {
  name: string
  description: string
  triggers: string[]
  tags: string[]
  body: string
}

function parseSkillMdPreview(content: string): PreviewData | null {
  const fmMatch = content.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/)
  if (!fmMatch) return null

  const fm = fmMatch[1]
  const body = fmMatch[2].trim()

  const nameMatch = fm.match(/^name:\s*(.+)$/m)
  const descMatch = fm.match(/^description:\s*(.+)$/m)

  // Parse triggers
  const triggersMatch = fm.match(/^triggers:\s*\n((?:\s+-\s*.+\n?)*)/m)
  const triggers = triggersMatch
    ? triggersMatch[1].split('\n').map((l) => l.replace(/^\s*-\s*/, '').trim()).filter(Boolean)
    : []

  // Parse tags
  const tagsMatch = fm.match(/^tags:\s*\[(.+)\]/m)
  const tags = tagsMatch ? tagsMatch[1].split(',').map((t) => t.trim()) : []

  return {
    name: nameMatch?.[1]?.trim() ?? 'Untitled',
    description: descMatch?.[1]?.trim() ?? '',
    triggers,
    tags,
    body,
  }
}

function parseYamlPreview(content: string): PreviewData | null {
  const nameMatch = content.match(/^name:\s*(.+)$/m)
  if (!nameMatch) return null

  const triggersMatch = content.match(/^triggers:\s*\n((?:\s+-\s*.+\n?)*)/m)
  const triggers = triggersMatch
    ? triggersMatch[1].split('\n').map((l) => l.replace(/^\s*-\s*/, '').trim()).filter(Boolean)
    : []

  return {
    name: nameMatch[1].trim(),
    description: '',
    triggers,
    tags: [],
    body: content,
  }
}
