import { useState, useRef, useEffect } from 'react'
import { Send, Trash2, AlertCircle, ChevronDown } from 'lucide-react'
import { useApi } from '@/hooks/use-api'
import { useAuth } from '@/hooks/use-auth'
import { api } from '@/lib/api'
import { emptyTrail, streamChat, withEvent, type Trail } from '@/lib/chat-stream'
import { ChatMessage, type ChatMsg } from '@/components/chat-message'
import { cn } from '@/lib/utils'
import { safeRandomUUID } from '@/lib/uuid'

interface Venture {
  key: string
  name: string
  agent_count: number
}

interface VenturesResponse {
  ventures: Venture[]
}

interface AgentsResponse {
  agents: Array<{ key: string }>
}

interface ConversationResponse {
  messages: Array<{
    id?: number | null
    role: string
    content: string
    created_at?: string
    trail?: Trail
  }>
}

function getSessionUserId(): string {
  const key = 'realize_session_user_id'
  let id = localStorage.getItem(key)
  if (!id) {
    // `crypto.randomUUID()` is Secure-Context-only, so this page would crash
    // on plain-HTTP deployments without the fallback inside safeRandomUUID.
    id = `user-${safeRandomUUID().slice(0, 8)}`
    localStorage.setItem(key, id)
  }
  return id
}

/** Used only when auth is off; signed-in users chat as themselves. */
const FALLBACK_USER_ID = getSessionUserId()

/** Stored timestamps are "YYYY-MM-DD HH:MM:SS"; make them parseable everywhere. */
function toIso(created?: string): string | undefined {
  return created ? created.replace(' ', 'T') : undefined
}

export default function ChatPage() {
  const { user } = useAuth()
  const userId = user?.user_id ?? FALLBACK_USER_ID
  const { data: venturesData } = useApi<VenturesResponse>('/ventures')
  const [selectedVenture, setSelectedVenture] = useState('')
  const [selectedAgent, setSelectedAgent] = useState('')
  const [agents, setAgents] = useState<Array<{ key: string }>>([])
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Stop a running stream when leaving the page
  useEffect(() => () => abortRef.current?.abort(), [])

  // Auto-select first venture
  useEffect(() => {
    if (venturesData?.ventures.length && !selectedVenture) {
      const first = venturesData.ventures[0]
      if (first) setSelectedVenture(first.key)
    }
  }, [venturesData, selectedVenture])

  // Load agents when venture changes
  useEffect(() => {
    if (!selectedVenture) return
    api
      .get<AgentsResponse>(`/ventures/${selectedVenture}/agents`)
      .then((data) => setAgents(data.agents || []))
      .catch(() => setAgents([]))
  }, [selectedVenture])

  // Load conversation history when venture changes
  useEffect(() => {
    if (!selectedVenture) return
    api
      .get<ConversationResponse>(`/conversations/${selectedVenture}/${userId}`)
      .then((data) => {
        const msgs: ChatMsg[] = (data.messages || []).map((m) => ({
          role: m.role === 'user' ? ('user' as const) : ('assistant' as const),
          content: m.content,
          timestamp: toIso(m.created_at),
          id: m.id,
          trail: m.trail,
        }))
        setMessages(msgs)
      })
      .catch(() => setMessages([]))
  }, [selectedVenture, userId])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  async function handleSend() {
    if (!input.trim() || !selectedVenture || sending) return

    const userMsg: ChatMsg = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date().toISOString(),
    }

    // The answer appears at once as a pending bubble; its trail fills in live.
    const localKey = `pending-${Date.now()}`
    const pendingMsg: ChatMsg = {
      role: 'assistant',
      content: '',
      pending: true,
      localKey,
      trail: emptyTrail(),
    }
    const updatePending = (patch: (m: ChatMsg) => ChatMsg) =>
      setMessages((prev) => prev.map((m) => (m.localKey === localKey ? patch(m) : m)))
    const dropPending = () => setMessages((prev) => prev.filter((m) => m.localKey !== localKey))

    setMessages((prev) => [...prev, userMsg, pendingMsg])
    setInput('')
    setSending(true)
    setError('')
    const controller = new AbortController()
    abortRef.current = controller

    try {
      await streamChat(
        {
          message: userMsg.content,
          system_key: selectedVenture,
          user_id: userId,
          agent_key: selectedAgent || undefined,
          channel: 'dashboard',
        },
        (event) => {
          if (event.type === 'final') {
            updatePending((m) => ({
              ...m,
              content: event.response,
              agent_key: event.agent_key,
              id: event.message_id,
              trail: event.trail,
              pending: false,
              timestamp: new Date().toISOString(),
            }))
          } else if (event.type === 'error') {
            setError(event.detail)
            dropPending()
          } else {
            updatePending((m) => ({ ...m, trail: withEvent(m.trail ?? emptyTrail(), event) }))
          }
        },
        controller.signal,
      )
    } catch (err) {
      if (controller.signal.aborted) return
      setError(err instanceof Error ? err.message : 'Failed to send message')
      dropPending()
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
  }

  async function handleClear() {
    if (!selectedVenture) return
    try {
      await api.delete(`/conversations/${selectedVenture}/${userId}`)
      setMessages([])
    } catch {
      // ignore
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const ventures = venturesData?.ventures || []

  return (
    <div className="flex flex-col h-[calc(100vh-3rem)] -m-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-4 pb-4 border-b border-border shrink-0">
        <h1 className="text-2xl font-bold text-foreground">Chat</h1>
        <div className="flex items-center gap-3">
          {/* Venture selector */}
          <div className="relative">
            <select
              value={selectedVenture}
              onChange={(e) => {
                setSelectedVenture(e.target.value)
                setSelectedAgent('')
                setMessages([])
              }}
              className="appearance-none bg-surface-800 border border-border rounded-lg px-3 py-1.5 pr-8 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
            >
              <option value="">Select venture...</option>
              {ventures.map((v) => (
                <option key={v.key} value={v.key}>
                  {v.name}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
          </div>

          {/* Agent selector */}
          {agents.length > 0 && (
            <div className="relative">
              <select
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
                className="appearance-none bg-surface-800 border border-border rounded-lg px-3 py-1.5 pr-8 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-brand-400"
              >
                <option value="">Auto-route</option>
                {agents.map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.key}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
            </div>
          )}

          {/* Clear button */}
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-muted-foreground hover:text-red-400 border border-border rounded-lg hover:border-red-400/30 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto py-6 space-y-4">
        {messages.length === 0 && !sending && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="text-4xl mb-4 opacity-20 rz-animate-float">💬</div>
            <h2 className="text-lg font-medium text-foreground mb-1">Start a conversation</h2>
            <p className="text-sm text-muted-foreground max-w-md">
              {selectedVenture
                ? `Send a message to your ${selectedVenture} agents. They'll route it to the best agent automatically.`
                : 'Select a venture to start chatting.'}
            </p>
          </div>
        )}

        {messages.map((msg, i) => {
          const key =
            msg.localKey ?? (msg.id != null ? `m-${msg.id}` : `${msg.timestamp}-${msg.role}-${i}`)
          return <ChatMessage key={key} msg={msg} anchorPrefix={`trail-${key}`} />
        })}

        {error && (
          <div className="flex items-center gap-2 text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-2 max-w-3xl">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div
        className="shrink-0 border-t border-border pt-4 fx-glass"
        style={{ margin: '0 -24px', padding: '16px 24px 0' }}
      >
        <div className="flex gap-3 max-w-3xl">
          <textarea
            ref={inputRef}
            value={input}
            maxLength={4096}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              selectedVenture
                ? 'Type a message... (Enter to send, Shift+Enter for newline)'
                : 'Select a venture first...'
            }
            disabled={!selectedVenture || sending}
            rows={1}
            className={cn(
              'flex-1 resize-none rounded-xl border border-border bg-surface-800 px-4 py-3 text-sm text-foreground',
              'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand-400',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
            style={{ minHeight: '44px', maxHeight: '120px' }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = 'auto'
              target.style.height = Math.min(target.scrollHeight, 120) + 'px'
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !selectedVenture || sending}
            className={cn(
              'flex items-center justify-center rounded-xl px-4 py-3 text-sm font-medium transition-colors',
              'bg-brand-400 text-black hover:bg-brand-400/90',
              'disabled:opacity-40 disabled:cursor-not-allowed',
            )}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        {input.length > 3500 && (
          <div className="text-xs text-muted-foreground mt-1 text-right">{input.length}/4096</div>
        )}
      </div>
    </div>
  )
}
