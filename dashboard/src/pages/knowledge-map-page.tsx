import { useState, useMemo } from 'react'
import {
  Brain,
  Search,
  Tag,
  Link2,
  FileText,
  Users,
  Lightbulb,
  AlertTriangle,
  Zap,
  RefreshCw,
  ChevronRight,
  BarChart3,
  Network,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { useDebounce } from '@/hooks/use-debounce'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

/* ─── Types ──────────────────────────────────────────────────────── */

interface EntityTocEntry {
  id: string
  type: string
  title: string
  slug: string
  venture: string
  tags: string[]
  refs: string[]
  layer: string
  source: string
  confidence: number
  verified: boolean
}

interface TocResponse {
  toc: EntityTocEntry[]
  count: number
}

interface SearchResult {
  id: string
  type: string
  title: string
  venture: string
  snippet?: string
}

interface SearchResponse {
  results: SearchResult[]
  count: number
  query: string
}

interface StatsResponse {
  stats: Record<string, number | string>
}

/* ─── Type metadata ──────────────────────────────────────────────── */

const typeConfig: Record<string, { icon: typeof FileText; color: string }> = {
  decision: { icon: Zap, color: 'text-amber-400 bg-amber-400/10' },
  mission: { icon: Zap, color: 'text-blue-400 bg-blue-400/10' },
  contact: { icon: Users, color: 'text-emerald-400 bg-emerald-400/10' },
  commitment: { icon: ShieldCheck, color: 'text-violet-400 bg-violet-400/10' },
  insight: { icon: Lightbulb, color: 'text-yellow-400 bg-yellow-400/10' },
  risk: { icon: AlertTriangle, color: 'text-red-400 bg-red-400/10' },
  action: { icon: Zap, color: 'text-cyan-400 bg-cyan-400/10' },
  document: { icon: FileText, color: 'text-gray-400 bg-gray-400/10' },
  learning: { icon: Lightbulb, color: 'text-pink-400 bg-pink-400/10' },
}
const fallbackTypeConfig = typeConfig.document!

/* ─── Layer badge ────────────────────────────────────────────────── */

const layerColors: Record<string, string> = {
  foundations: 'text-amber-400 bg-amber-400/10',
  agents: 'text-blue-400 bg-blue-400/10',
  brain: 'text-violet-400 bg-violet-400/10',
  routines: 'text-emerald-400 bg-emerald-400/10',
  insights: 'text-yellow-400 bg-yellow-400/10',
  creations: 'text-pink-400 bg-pink-400/10',
}

/* ─── Entity card ────────────────────────────────────────────────── */

function EntityCard({ entity }: { entity: EntityTocEntry | SearchResult }) {
  const [expanded, setExpanded] = useState(false)
  const cfg = typeConfig[entity.type] ?? fallbackTypeConfig
  const Icon = cfg.icon
  const tags = 'tags' in entity ? (entity as EntityTocEntry).tags : []
  const refs = 'refs' in entity ? (entity as EntityTocEntry).refs : []
  const layer = 'layer' in entity ? (entity as EntityTocEntry).layer : ''
  const confidence = 'confidence' in entity ? (entity as EntityTocEntry).confidence : 1
  const verified = 'verified' in entity ? (entity as EntityTocEntry).verified : false

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card p-3 transition-all duration-200',
        'hover:border-brand-400/30 hover:shadow-lg hover:shadow-brand-400/5',
        expanded && 'ring-1 ring-brand-400/20',
      )}
    >
      <div className="flex items-start gap-3">
        <div className={cn('rounded-lg p-1.5 flex-shrink-0', cfg.color)}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <h3 className="text-sm font-semibold text-foreground truncate">{entity.title}</h3>
            {verified && <ShieldCheck className="h-3.5 w-3.5 text-emerald-400 flex-shrink-0" />}
            {confidence < 0.7 && (
              <ShieldAlert className="h-3.5 w-3.5 text-amber-400 flex-shrink-0">
                <title>{`Confidence: ${(confidence * 100).toFixed(0)}%`}</title>
              </ShieldAlert>
            )}
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
            <span
              className={cn(
                'px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold tracking-wide',
                cfg.color,
              )}
            >
              {entity.type}
            </span>
            {entity.venture && (
              <span className="bg-surface-700 px-1.5 py-0.5 rounded">{entity.venture}</span>
            )}
            {layer && (
              <span
                className={cn(
                  'px-1.5 py-0.5 rounded text-[10px] uppercase',
                  layerColors[layer] || 'bg-surface-700',
                )}
              >
                {layer.slice(0, 1).toUpperCase()}
              </span>
            )}
            {refs.length > 0 && (
              <span className="flex items-center gap-0.5">
                <Link2 className="h-3 w-3" />
                {refs.length}
              </span>
            )}
          </div>

          {/* Tags */}
          {tags.length > 0 && (
            <div className="flex items-center gap-1 mt-1.5 flex-wrap">
              <Tag className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              {tags.slice(0, 5).map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] bg-surface-700 text-muted-foreground px-1.5 py-0.5 rounded"
                >
                  {tag}
                </span>
              ))}
              {tags.length > 5 && (
                <span className="text-[10px] text-muted-foreground">+{tags.length - 5}</span>
              )}
            </div>
          )}
        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="rounded-lg p-1 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors flex-shrink-0"
          aria-label={expanded ? 'Collapse' : 'Expand'}
        >
          <ChevronRight className={cn('h-4 w-4 transition-transform', expanded && 'rotate-90')} />
        </button>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-border space-y-2 text-xs">
          <div className="font-mono text-muted-foreground">{entity.id}</div>
          {refs.length > 0 && (
            <div>
              <span className="text-muted-foreground font-medium">References:</span>
              <div className="flex flex-wrap gap-1 mt-1">
                {refs.map((ref) => (
                  <span
                    key={ref}
                    className="bg-blue-400/10 text-blue-400 px-1.5 py-0.5 rounded font-mono text-[10px]"
                  >
                    {ref}
                  </span>
                ))}
              </div>
            </div>
          )}
          {confidence < 1.0 && (
            <div className="text-muted-foreground">
              Confidence: {(confidence * 100).toFixed(0)}% · Source:{' '}
              {'source' in entity ? (entity as EntityTocEntry).source : 'manual'}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ─── Page ────────────────────────────────────────────────────────── */

export default function KnowledgeMapPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [ventureFilter, setVentureFilter] = useState('')

  const debouncedSearch = useDebounce(searchQuery, 400)

  // Fetch TOC (always loaded)
  const {
    data: tocData,
    loading: tocLoading,
    refetch: refetchToc,
  } = useApi<TocResponse>(`/fabric/toc${ventureFilter ? `?venture=${ventureFilter}` : ''}`, 30000)

  // Fetch search results (only when searching)
  const { data: searchData, loading: searchLoading } = useApi<SearchResponse>(
    debouncedSearch
      ? `/fabric/search?q=${encodeURIComponent(debouncedSearch)}&n=20${ventureFilter ? `&venture=${ventureFilter}` : ''}`
      : '/fabric/stats',
    30000,
  )

  // Fetch stats
  const { refetch: refetchStats } = useApi<StatsResponse>(
    `/fabric/stats${ventureFilter ? `?venture=${ventureFilter}` : ''}`,
  )

  const handleRefresh = async () => {
    await api.post(`/fabric/reindex${ventureFilter ? `?venture=${ventureFilter}` : ''}`)
    refetchToc()
    refetchStats()
  }

  const isSearching = Boolean(debouncedSearch)
  const loading = isSearching ? searchLoading : tocLoading

  // Filter TOC entries
  const filteredEntries = useMemo(() => {
    if (!tocData?.toc) return []
    let entries = tocData.toc
    if (typeFilter) {
      entries = entries.filter((e) => e.type === typeFilter)
    }
    return entries
  }, [tocData, typeFilter])

  // Extract unique types from TOC for filter
  const availableTypes = useMemo(() => {
    if (!tocData?.toc) return []
    const types = new Set(tocData.toc.map((e) => e.type))
    return Array.from(types).sort()
  }, [tocData])

  // Type distribution for the mini chart
  const typeDistribution = useMemo(() => {
    if (!tocData?.toc) return []
    const counts: Record<string, number> = {}
    tocData.toc.forEach((e) => {
      counts[e.type] = (counts[e.type] || 0) + 1
    })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
  }, [tocData])

  return (
    <div className="space-y-6 rz-animate-fade-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="h-6 w-6 text-brand-400" />
          <h1 className="text-2xl font-bold text-foreground">Knowledge Map</h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
            aria-label="Reindex and refresh"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-xl border border-border bg-card p-3 fx-glass">
          <div className="flex items-center gap-2 mb-1">
            <FileText className="h-4 w-4 text-brand-400" />
            <span className="text-xs text-muted-foreground">Entities</span>
          </div>
          <div className="text-lg font-bold text-foreground">{tocData?.count || 0}</div>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 fx-glass">
          <div className="flex items-center gap-2 mb-1">
            <Network className="h-4 w-4 text-violet-400" />
            <span className="text-xs text-muted-foreground">Types</span>
          </div>
          <div className="text-lg font-bold text-foreground">{availableTypes.length}</div>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 fx-glass">
          <div className="flex items-center gap-2 mb-1">
            <Link2 className="h-4 w-4 text-emerald-400" />
            <span className="text-xs text-muted-foreground">References</span>
          </div>
          <div className="text-lg font-bold text-foreground">
            {tocData?.toc?.reduce((sum, e) => sum + (e.refs?.length || 0), 0) || 0}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 fx-glass">
          <div className="flex items-center gap-2 mb-1">
            <ShieldCheck className="h-4 w-4 text-amber-400" />
            <span className="text-xs text-muted-foreground">Verified</span>
          </div>
          <div className="text-lg font-bold text-foreground">
            {tocData?.toc?.filter((e) => e.verified).length || 0}
          </div>
        </div>
      </div>

      {/* Type distribution bar */}
      {typeDistribution.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4 fx-glass">
          <div className="flex items-center gap-2 mb-3">
            <BarChart3 className="h-4 w-4 text-muted-foreground" />
            <span className="text-xs font-medium text-muted-foreground">Entity Distribution</span>
          </div>
          <div className="space-y-2">
            {typeDistribution.map(([type, count]) => {
              const cfg = typeConfig[type] ?? fallbackTypeConfig
              const pct = tocData?.count ? (count / tocData.count) * 100 : 0
              return (
                <div key={type} className="flex items-center gap-3">
                  <span
                    className={cn('text-xs font-medium w-24 truncate', cfg.color.split(' ')[0])}
                  >
                    {type}
                  </span>
                  <div className="flex-1 h-2 rounded-full bg-surface-700 overflow-hidden">
                    <div
                      className={cn(
                        'h-full rounded-full transition-all duration-500',
                        cfg.color.split(' ')[1]?.replace('/10', '/40') || 'bg-brand-400/40',
                      )}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground font-mono w-8 text-right">
                    {count}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Search + Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search knowledge base..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={cn(
              'w-full rounded-lg border border-border bg-surface-800 pl-9 pr-3 py-2 text-sm text-foreground',
              'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400',
            )}
          />
        </div>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-2 text-xs text-foreground',
            'focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        >
          <option value="">All types</option>
          {availableTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input
          type="text"
          placeholder="Venture"
          value={ventureFilter}
          onChange={(e) => setVentureFilter(e.target.value)}
          className={cn(
            'rounded-lg border border-border bg-surface-800 px-3 py-2 text-xs text-foreground',
            'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400',
          )}
        />
      </div>

      {/* Results */}
      <div className="space-y-2">
        {loading ? (
          <div className="rounded-xl border border-border bg-card p-8 text-center text-muted-foreground text-sm">
            Loading knowledge map...
          </div>
        ) : isSearching && searchData && 'results' in searchData ? (
          <>
            <p className="text-xs text-muted-foreground">
              {(searchData as SearchResponse).count} result(s) for "{debouncedSearch}"
            </p>
            {(searchData as SearchResponse).results.map((r) => (
              <EntityCard key={r.id} entity={r as unknown as EntityTocEntry} />
            ))}
          </>
        ) : (
          <>
            <p className="text-xs text-muted-foreground">
              {filteredEntries.length} entit{filteredEntries.length === 1 ? 'y' : 'ies'}
              {typeFilter && ` of type "${typeFilter}"`}
            </p>
            {filteredEntries.map((entry) => (
              <EntityCard key={entry.id} entity={entry} />
            ))}
          </>
        )}

        {!loading && filteredEntries.length === 0 && !isSearching && (
          <div className="rounded-xl border border-border bg-card p-12 text-center">
            <Brain className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
            <h3 className="text-sm font-medium text-foreground mb-1">Knowledge map is empty</h3>
            <p className="text-xs text-muted-foreground">
              Run{' '}
              <code className="bg-surface-700 px-1.5 py-0.5 rounded text-[10px]">
                realize-os fabric reindex
              </code>{' '}
              to populate the index.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
