import { useState } from 'react'
import {
  Folder,
  FolderOpen,
  FileText,
  Search,
  ChevronRight,
  ChevronDown,
  Pencil,
  Plus,
  Link,
  Loader2,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { FileEditor, CreateFileDialog } from '@/components/file-editor'

interface KBFile {
  name: string
  relative_path: string
  size: number
}

interface KBTree {
  [dir: string]: {
    exists: boolean
    files: KBFile[]
  }
}

interface KBFilesResponse {
  venture_key: string
  tree: KBTree
}

interface KBFileContent {
  path: string
  content: string
  size: number
}

interface KBSearchResult {
  query: string
  results: Array<{
    path: string
    title: string
    snippet: string
    score: number
  }>
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  return `${(bytes / 1024).toFixed(1)} KB`
}

function FabricDir({
  label,
  data,
  onFileClick,
  onCreateFile,
  selectedPath,
}: {
  label: string
  data: { exists: boolean; files: KBFile[] }
  onFileClick: (path: string) => void
  onCreateFile: (dir: string) => void
  selectedPath: string | null
}) {
  const [open, setOpen] = useState(false)

  if (!data.exists) {
    return (
      <div className="flex items-center gap-2 py-1 text-muted-foreground/50">
        <Folder className="h-4 w-4" />
        <span className="text-sm">{label}</span>
        <span className="text-xs">(empty)</span>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => setOpen(!open)}
          className="flex items-center gap-2 py-1 flex-1 text-left hover:text-foreground text-muted-foreground transition-colors"
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          {open ? (
            <FolderOpen className="h-4 w-4 text-brand-400" />
          ) : (
            <Folder className="h-4 w-4 text-brand-400" />
          )}
          <span className="text-sm font-medium">{label}</span>
          <span className="text-xs text-muted-foreground">({data.files.length})</span>
        </button>
        {open && (
          <button
            onClick={() => onCreateFile(label)}
            className="p-0.5 rounded text-muted-foreground/50 hover:text-brand-400 transition-colors"
            title="New file"
          >
            <Plus className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {open && (
        <div className="ml-6 border-l border-border pl-3 space-y-0.5">
          {data.files.map((f) => (
            <button
              key={f.relative_path}
              onClick={() => onFileClick(f.relative_path)}
              className={cn(
                'flex items-center gap-2 py-1 w-full text-left transition-colors',
                selectedPath === f.relative_path
                  ? 'text-brand-400'
                  : 'text-muted-foreground hover:text-brand-400',
              )}
            >
              <FileText className="h-3.5 w-3.5" />
              <span className="text-sm truncate">{f.name}</span>
              <span className="text-xs text-muted-foreground/60 ml-auto shrink-0">{formatSize(f.size)}</span>
            </button>
          ))}
          {data.files.length === 0 && (
            <p className="text-xs text-muted-foreground/50 py-1">No files</p>
          )}
        </div>
      )}
    </div>
  )
}

export function KBBrowser({ ventureKey }: { ventureKey: string }) {
  const { data, loading, refetch } = useApi<KBFilesResponse>(`/ventures/${ventureKey}/kb/files`)
  const [selectedFile, setSelectedFile] = useState<KBFileContent | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<KBSearchResult | null>(null)
  const [searching, setSearching] = useState(false)
  const [creatingIn, setCreatingIn] = useState<string | null>(null)
  const [showIngest, setShowIngest] = useState(false)
  const [ingestUrl, setIngestUrl] = useState('')
  const [ingesting, setIngesting] = useState(false)
  const [ingestStatus, setIngestStatus] = useState<string | null>(null)

  async function openFile(path: string) {
    setFileLoading(true)
    setSearchResults(null)
    setEditMode(false)
    try {
      const content = await api.get<KBFileContent>(`/ventures/${ventureKey}/kb/file?path=${encodeURIComponent(path)}`)
      setSelectedFile(content)
    } catch {
      setSelectedFile({ path, content: 'Failed to load file', size: 0 })
    } finally {
      setFileLoading(false)
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim()) return
    setSearching(true)
    setSelectedFile(null)
    setEditMode(false)
    try {
      const results = await api.get<KBSearchResult>(`/ventures/${ventureKey}/kb/search?q=${encodeURIComponent(searchQuery)}`)
      setSearchResults(results)
    } catch {
      setSearchResults({ query: searchQuery, results: [] })
    } finally {
      setSearching(false)
    }
  }

  function getCreateDir(label: string): string {
    if (!data?.tree[label]) return ''
    const files = data.tree[label].files
    if (files.length > 0) {
      const firstPath = files[0].relative_path
      return firstPath.substring(0, firstPath.lastIndexOf('/'))
    }
    return ''
  }

  function getExtension(label: string): '.md' | '.yaml' {
    return label === 'R-routines' ? '.yaml' : '.md'
  }

  async function handleIngest() {
    if (!ingestUrl.trim()) return
    setIngesting(true)
    setIngestStatus(null)
    try {
      const res = await api.post<{ title: string; char_count: number }>(`/ventures/${ventureKey}/ingest`, { url: ingestUrl.trim() })
      setIngestStatus(`Ingested "${res.title}" (${res.char_count} chars)`)
      setIngestUrl('')
      refetch()
    } catch (err) {
      setIngestStatus(err instanceof Error ? err.message : 'Ingestion failed')
    } finally {
      setIngesting(false)
    }
  }

  if (loading) {
    return <div className="text-sm text-muted-foreground py-4">Loading knowledge base...</div>
  }

  const tree = data?.tree || {}

  return (
    <div className="rounded-xl border border-border bg-card">
      {/* Search bar */}
      <div className="flex gap-2 p-4 border-b border-border">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search knowledge base..."
            className="w-full rounded-lg border border-border bg-surface-800 pl-9 pr-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={searching || !searchQuery.trim()}
          className="px-3 py-2 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40 transition-colors"
        >
          Search
        </button>
        <button
          onClick={() => setShowIngest(!showIngest)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border transition-colors',
            showIngest ? 'border-brand-400 text-brand-400' : 'border-border text-muted-foreground hover:text-foreground',
          )}
          title="Ingest URL into knowledge base"
        >
          <Link className="h-4 w-4" />
          Ingest
        </button>
      </div>
      {showIngest && (
        <div className="flex gap-2 px-4 pb-3">
          <input
            value={ingestUrl}
            onChange={(e) => setIngestUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleIngest()}
            placeholder="Paste a URL to extract content into the brain..."
            className="flex-1 rounded-lg border border-border bg-surface-800 px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
          />
          <button
            onClick={handleIngest}
            disabled={ingesting || !ingestUrl.trim()}
            className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40 transition-colors"
          >
            {ingesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link className="h-4 w-4" />}
            {ingesting ? 'Ingesting...' : 'Extract'}
          </button>
          {ingestStatus && (
            <span className="self-center text-xs text-muted-foreground">{ingestStatus}</span>
          )}
        </div>
      )}

      <div className="flex divide-x divide-border" style={{ minHeight: '400px' }}>
        {/* File tree */}
        <div className="w-64 shrink-0 p-4 space-y-1 overflow-y-auto" style={{ maxHeight: '600px' }}>
          {Object.entries(tree).map(([dir, dirData]) => (
            <FabricDir
              key={dir}
              label={dir}
              data={dirData}
              onFileClick={openFile}
              onCreateFile={(label) => setCreatingIn(label)}
              selectedPath={selectedFile?.path || null}
            />
          ))}
          {creatingIn && (
            <div className="mt-2">
              <CreateFileDialog
                ventureKey={ventureKey}
                directory={getCreateDir(creatingIn)}
                extension={getExtension(creatingIn)}
                onCreated={() => { setCreatingIn(null); refetch() }}
                onCancel={() => setCreatingIn(null)}
              />
            </div>
          )}
        </div>

        {/* Content / Editor */}
        <div className="flex-1 p-4 overflow-y-auto" style={{ maxHeight: '600px' }}>
          {fileLoading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {selectedFile && !fileLoading && editMode && (
            <FileEditor
              ventureKey={ventureKey}
              filePath={selectedFile.path}
              initialContent={selectedFile.content}
              onClose={() => setEditMode(false)}
              onSaved={() => { refetch(); openFile(selectedFile.path) }}
              onDeleted={() => { setSelectedFile(null); setEditMode(false); refetch() }}
            />
          )}

          {selectedFile && !fileLoading && !editMode && (
            <div>
              <div className="flex items-center justify-between mb-3">
                <span className="text-xs text-muted-foreground font-mono">{selectedFile.path}</span>
                <button
                  onClick={() => setEditMode(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:text-brand-400 hover:border-brand-400/30 transition-colors"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </button>
              </div>
              <pre className="text-sm text-foreground whitespace-pre-wrap font-mono bg-surface-800 rounded-lg p-4 border border-border overflow-auto">
                {selectedFile.content}
              </pre>
            </div>
          )}

          {searchResults && !selectedFile && (
            <div>
              <p className="text-xs text-muted-foreground mb-3">
                {searchResults.results.length} result(s) for &ldquo;{searchResults.query}&rdquo;
              </p>
              <div className="space-y-2">
                {searchResults.results.map((r, i) => (
                  <button
                    key={i}
                    onClick={() => openFile(r.path)}
                    className="w-full text-left rounded-lg border border-border p-3 hover:border-brand-400/30 transition-colors"
                  >
                    <div className="text-sm font-medium text-foreground">{r.title}</div>
                    <div className="text-xs text-muted-foreground font-mono">{r.path}</div>
                    {r.snippet && (
                      <div className="text-xs text-muted-foreground mt-1 line-clamp-2">{r.snippet}</div>
                    )}
                  </button>
                ))}
                {searchResults.results.length === 0 && (
                  <p className="text-sm text-muted-foreground">No results found.</p>
                )}
              </div>
            </div>
          )}

          {!selectedFile && !searchResults && !fileLoading && (
            <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
              Select a file to view or edit, or search the knowledge base
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
