import { useNavigate } from 'react-router-dom'
import { Wrench, Wifi, WifiOff, Globe, Monitor, Mail, Calendar, HardDrive, Radio, AlertCircle, Webhook } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { cn } from '@/lib/utils'

interface Tool {
  name: string
  description: string
  category: string
  available: boolean
  actions: string[]
}

interface Channel {
  name: string
  type: string
  enabled: boolean
}

interface MCPServer {
  name: string
  connected: boolean
  tools_count: number
}

interface ToolsData {
  tools: Tool[]
  google_workspace: { gmail: boolean; calendar: boolean; drive: boolean }
  mcp_servers: MCPServer[]
  browser_enabled: boolean
  channels: Channel[]
}

function StatusDot({ active }: { active: boolean }) {
  return (
    <span className={cn(
      'inline-block h-2 w-2 rounded-full',
      active ? 'bg-green-400' : 'bg-surface-600',
    )} />
  )
}

export default function ToolsPage() {
  const navigate = useNavigate()
  const { data, loading, error } = useApi<ToolsData>('/tools')

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-muted-foreground">Loading tools...</div>
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64 text-red-400 gap-2">
        <AlertCircle className="h-5 w-5" />
        Failed to load tools
      </div>
    )
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-2">
        <Wrench className="h-6 w-6 text-brand-400" />
        <h1 className="text-2xl font-bold text-foreground">Tools & Integrations</h1>
      </div>

      {/* Registered Tools */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Registered Tools</h2>
        {data.tools.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tools registered</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {data.tools.map((tool) => (
              <div key={tool.name} className="rounded-lg border border-border p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Globe className="h-4 w-4 text-brand-400" />
                    <span className="text-sm font-medium text-foreground capitalize">{tool.name}</span>
                  </div>
                  <span className={cn(
                    'text-xs px-2 py-0.5 rounded-full',
                    tool.available ? 'bg-green-400/10 text-green-400' : 'bg-surface-700 text-muted-foreground',
                  )}>
                    {tool.available ? 'Active' : 'Inactive'}
                  </span>
                </div>
                {tool.description && (
                  <p className="text-xs text-muted-foreground mb-2">{tool.description}</p>
                )}
                <div className="flex flex-wrap gap-1">
                  {tool.actions.map((a) => (
                    <span key={a} className="text-[10px] px-1.5 py-0.5 rounded bg-surface-700 text-muted-foreground font-mono">
                      {a}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Google Workspace */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Google Workspace</h2>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="flex items-center gap-3 rounded-lg border border-border p-3">
            <Mail className="h-5 w-5 text-muted-foreground" />
            <div className="flex-1">
              <div className="text-sm text-foreground">Gmail</div>
              <div className="text-xs text-muted-foreground">Send, read, search emails</div>
            </div>
            <StatusDot active={data.google_workspace.gmail} />
          </div>
          <div className="flex items-center gap-3 rounded-lg border border-border p-3">
            <Calendar className="h-5 w-5 text-muted-foreground" />
            <div className="flex-1">
              <div className="text-sm text-foreground">Calendar</div>
              <div className="text-xs text-muted-foreground">Events, scheduling</div>
            </div>
            <StatusDot active={data.google_workspace.calendar} />
          </div>
          <div className="flex items-center gap-3 rounded-lg border border-border p-3">
            <HardDrive className="h-5 w-5 text-muted-foreground" />
            <div className="flex-1">
              <div className="text-sm text-foreground">Drive</div>
              <div className="text-xs text-muted-foreground">Files, docs, search</div>
            </div>
            <StatusDot active={data.google_workspace.drive} />
          </div>
        </div>
        {!data.google_workspace.gmail && (
          <p className="text-xs text-muted-foreground mt-3">
            <button onClick={() => navigate('/setup')} className="text-brand-400 hover:underline">Configure in Setup</button> — add Google Workspace credentials
          </p>
        )}
      </div>

      {/* MCP Servers */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">MCP Servers</h2>
        {data.mcp_servers.length === 0 ? (
          <div>
            <p className="text-sm text-muted-foreground">No MCP servers configured</p>
            <p className="text-xs text-muted-foreground mt-1">
              <button onClick={() => navigate('/setup')} className="text-brand-400 hover:underline">Enable in Setup</button> — toggle MCP Servers on
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {data.mcp_servers.map((s) => (
              <div key={s.name} className="flex items-center gap-3 rounded-lg border border-border p-3">
                {s.connected ? <Wifi className="h-4 w-4 text-green-400" /> : <WifiOff className="h-4 w-4 text-muted-foreground" />}
                <span className="text-sm text-foreground font-medium">{s.name}</span>
                <span className="text-xs text-muted-foreground ml-auto">{s.tools_count} tools</span>
                <StatusDot active={s.connected} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Browser */}
      <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Monitor className="h-5 w-5 text-muted-foreground" />
            <div>
              <h2 className="text-lg font-semibold text-foreground">Browser Tool</h2>
              <p className="text-xs text-muted-foreground">Navigate, click, extract, screenshot</p>
            </div>
          </div>
          <span className={cn(
            'text-xs px-2 py-0.5 rounded-full',
            data.browser_enabled ? 'bg-green-400/10 text-green-400' : 'bg-surface-700 text-muted-foreground',
          )}>
            {data.browser_enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
        {!data.browser_enabled && (
          <p className="text-xs text-muted-foreground mt-2">
            <button onClick={() => navigate('/setup')} className="text-brand-400 hover:underline">Enable in Setup</button> — toggle Browser Automation on
          </p>
        )}
      </div>

      {/* Channels */}
      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Channels</h2>
        <div className="space-y-2">
          {data.channels.map((ch) => (
            <div key={ch.name} className="flex items-center gap-3 rounded-lg border border-border p-3">
              <Radio className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm text-foreground font-medium">{ch.name}</span>
              <span className="text-xs text-muted-foreground font-mono">{ch.type}</span>
              <div className="ml-auto">
                <StatusDot active={ch.enabled} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Webhook Events */}
      <WebhookEventsSection />
    </div>
  )
}

interface WebhookEvent {
  source: string
  event_type: string
  received_at: string
  payload_size: number
}

function WebhookEventsSection() {
  const { data } = useApi<{ events: WebhookEvent[] }>('/webhooks/events')

  return (
    <div className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-center gap-2 mb-4">
        <Webhook className="h-5 w-5 text-brand-400" />
        <h2 className="text-lg font-semibold text-foreground">Webhook Events</h2>
      </div>
      {!data || data.events.length === 0 ? (
        <div>
          <p className="text-sm text-muted-foreground">No webhook events received yet.</p>
          <p className="text-xs text-muted-foreground mt-1">
            External services can send events to <code className="text-brand-400">POST /api/webhooks/{'{'} source {'}'}</code>
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {data.events.slice(0, 20).map((evt, i) => (
            <div key={i} className="flex items-center gap-3 rounded-lg border border-border p-3">
              <Webhook className="h-4 w-4 text-muted-foreground shrink-0" />
              <span className="text-sm text-foreground font-medium">{evt.source}</span>
              <span className="text-xs text-muted-foreground">{evt.event_type}</span>
              <span className="text-xs text-muted-foreground ml-auto">{new Date(evt.received_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
