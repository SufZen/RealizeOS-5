import { useState, useRef, useEffect } from 'react'
import { Send, Trash2, AlertCircle } from 'lucide-react'
import { EmptyState } from '@/components/ui/empty-state'
import { useAuth } from '@/hooks/use-auth'
import { useVenture } from '@/hooks/use-venture'
import { api } from '@/lib/api'
import { emptyTrail, streamChat, withEvent, type Trail } from '@/lib/chat-stream'
import { ChatMessage, type ChatMsg } from '@/components/chat-message'
import { cn } from '@/lib/utils'
import { safeRandomUUID } from '@/lib/uuid'

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
  const { selected: selectedVenture } = useVenture()
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

  // A different venture (global switcher) starts from its own agents and history.
  // A reply still streaming for the previous venture is stopped, not shown here.
  useEffect(() => {
    abortRef.current?.abort()
    setSelectedAgent('')
    setMessages([])
  }, [selectedVenture])

  // Load agents when venture changes (a late answer for another venture is dropped)
  useEffect(() => {
    if (!selectedVenture) return
    let current = true
    api
      .get<AgentsResponse>(`/ventures/${selectedVenture}/agents`)
      .then((data) => current && setAgents(data.agents || []))
      .catch(() => current && setAgents([]))
    return () => {
      current = false
    }
  }, [selectedVenture])

  // Load conversation history when venture changes (same rule)
  useEffect(() => {
    if (!selectedVenture) return
    let current = true
    api
      .get<ConversationResponse>(`/conversations/${selectedVenture}/${userId}`)
      .then((data) => {
        if (!current) return
        const msgs: ChatMsg[] = (data.messages || []).map((m) => ({
          role: m.role === 'user' ? ('user' as const) : ('assistant' as const),
          content: m.content,
          timestamp: toIso(m.created_at),
          id: m.id,
          trail: m.trail,
        }))
        setMessages(msgs)
      })
      .catch(() => current && setMessages([]))
    return () => {
      current = false
    }
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

  return (
    // Fills <main> edge to edge: cancels main's padding at each breakpoint; the
    // mobile header (3.5rem) only exists below md.
    <div className="-mx-4 -my-6 flex h-[calc(100dvh-3.5rem)] flex-col sm:-mx-8 sm:-my-8 md:h-dvh">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between gap-4 border-b border-border px-4 py-3 sm:px-8">
        <div className="min-w-0">
          <h1 className="m-0 text-lg font-semibold text-foreground">Chat</h1>
          {selectedVenture && (
            <p className="m-0 truncate text-xs text-subtle-foreground">
              Talking to the <bdi>{selectedVenture}</bdi> agents
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Agent selector */}
          {agents.length > 0 && (
            <select
              value={selectedAgent}
              onChange={(e) => setSelectedAgent(e.target.value)}
              aria-label="Agent"
              className="rz-select rz-input--sm w-auto"
            >
              <option value="">Auto-route</option>
              {agents.map((a) => (
                <option key={a.key} value={a.key}>
                  {a.key}
                </option>
              ))}
            </select>
          )}

          {/* Clear button */}
          {messages.length > 0 && (
            <button
              onClick={handleClear}
              className="rz-btn rz-btn--ghost rz-btn--sm hover:text-red-400"
            >
              <Trash2 aria-hidden />
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-8">
        <div className="mx-auto grid max-w-3xl gap-5">
          {messages.length === 0 && !sending && (
            <div className="pt-[12vh]">
              <EmptyState
                art="search"
                title="Start a conversation"
                body={
                  selectedVenture
                    ? `Send a message to your ${selectedVenture} agents. They'll route it to the best agent automatically.`
                    : 'Select a venture to start chatting.'
                }
              />
            </div>
          )}

          {messages.map((msg, i) => {
            const key =
              msg.localKey ?? (msg.id != null ? `m-${msg.id}` : `${msg.timestamp}-${msg.role}-${i}`)
            return <ChatMessage key={key} msg={msg} anchorPrefix={`trail-${key}`} />
          })}

          {error && (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-[7px] border border-red-400/30 bg-red-400/10 px-4 py-2 text-sm text-red-400"
            >
              <AlertCircle className="h-4 w-4 shrink-0" />
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-border bg-surface-950/60 px-4 py-3 sm:px-8">
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-[10px] border border-border-strong bg-card p-1.5 ps-3 transition-shadow focus-within:border-brand-400 focus-within:shadow-[0_0_0_3px_var(--rz-accent-soft)]">
          <textarea
            ref={inputRef}
            value={input}
            maxLength={4096}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            aria-label="Message"
            dir="auto"
            placeholder={selectedVenture ? 'Type a message...' : 'Select a venture first...'}
            disabled={!selectedVenture || sending}
            rows={1}
            className={cn(
              'flex-1 resize-none border-0 bg-transparent py-2 text-[15px] text-foreground outline-none',
              'placeholder:text-subtle-foreground disabled:cursor-not-allowed disabled:opacity-50',
            )}
            style={{ minHeight: '40px', maxHeight: '160px' }}
            onInput={(e) => {
              const target = e.target as HTMLTextAreaElement
              target.style.height = 'auto'
              target.style.height = Math.min(target.scrollHeight, 160) + 'px'
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || !selectedVenture || sending}
            className="rz-btn rz-btn--primary h-9 w-9 shrink-0 p-0"
            aria-busy={sending || undefined}
            aria-label="Send message"
          >
            <Send className="rtl:-scale-x-100" />
          </button>
        </div>
        <div className="mx-auto mt-1.5 hidden max-w-3xl justify-between text-xs text-subtle-foreground sm:flex">
          <span>
            <kbd className="rz-kbd">Enter</kbd> to send, <kbd className="rz-kbd">Shift</kbd> +{' '}
            <kbd className="rz-kbd">Enter</kbd> for a new line
          </span>
          {input.length > 3500 && <span className="tabular">{input.length}/4096</span>}
        </div>
        {input.length > 3500 && (
          <div className="mx-auto mt-1 max-w-3xl text-end text-xs tabular text-muted-foreground sm:hidden">
            {input.length}/4096
          </div>
        )}
      </div>
    </div>
  )
}
