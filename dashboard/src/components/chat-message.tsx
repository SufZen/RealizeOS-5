import { Bot, User } from 'lucide-react'
import { cn } from '@/lib/utils'
import { sourceAnchorId, splitCitations, type Trail } from '@/lib/chat-stream'
import { TrailPanel } from '@/components/trail-panel'

export interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  agent_key?: string
  timestamp?: string
  /** Stored message id (assistant answers). */
  id?: number | null
  /** "What I used": sources and tool steps behind an answer. */
  trail?: Trail
  /** True while the answer is still being prepared (streaming). */
  pending?: boolean
  /** Client-side key for a message that has no stored id yet. */
  localKey?: string
}

/** Sources an answer may cite, and where their footnote targets live. */
interface CiteContext {
  known: Set<string>
  anchorPrefix: string
}

/* ---- [Sn] footnotes ---- */

function renderCitations(text: string, key: number, cite: CiteContext | null): React.ReactNode {
  if (!cite || cite.known.size === 0) return <span key={key}>{text}</span>
  return (
    <span key={key}>
      {splitCitations(text).map((part, i) => {
        if (typeof part === 'string') return part
        if (!cite.known.has(part.marker)) return `[${part.marker}]`
        const target = sourceAnchorId(cite.anchorPrefix, part.marker)
        return (
          <sup key={i}>
            <button
              type="button"
              onClick={() =>
                document
                  .getElementById(target)
                  ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
              }
              className="px-0.5 font-mono text-brand-400 hover:underline"
              aria-label={`Source ${part.marker}`}
            >
              {part.marker}
            </button>
          </sup>
        )
      })}
    </span>
  )
}

/* ---- Lightweight markdown rendering ---- */

function renderMarkdown(text: string, cite: CiteContext | null): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g
  let lastIndex = 0
  let key = 0

  // First pass: split by code blocks
  let match: RegExpExecArray | null
  while ((match = codeBlockRegex.exec(text)) !== null) {
    // Add text before the code block
    if (match.index > lastIndex) {
      nodes.push(...renderInline(text.slice(lastIndex, match.index), key, cite))
      key += 100
    }
    // Add the code block
    const lang = match[1] || 'plain'
    nodes.push(
      <pre
        key={`code-${key++}`}
        className="bg-surface-800 border border-border rounded-lg p-3 text-xs font-mono overflow-x-auto my-2"
      >
        <div className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">
          {lang}
        </div>
        <code>{match[2]}</code>
      </pre>,
    )
    lastIndex = match.index + match[0].length
  }

  // Add remaining text after last code block
  if (lastIndex < text.length) {
    nodes.push(...renderInline(text.slice(lastIndex), key, cite))
  }

  return nodes
}

function renderInline(text: string, startKey: number, cite: CiteContext | null): React.ReactNode[] {
  if (!text) return []

  // Split by inline patterns: **bold**, *italic*, `inline code`
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/)

  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={startKey + i} className="font-semibold">
          {part.slice(2, -2)}
        </strong>
      )
    }
    if (part.startsWith('*') && part.endsWith('*') && !part.startsWith('**')) {
      return <em key={startKey + i}>{part.slice(1, -1)}</em>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code
          key={startKey + i}
          className="bg-surface-800 px-1.5 py-0.5 rounded text-xs font-mono text-brand-400"
        >
          {part.slice(1, -1)}
        </code>
      )
    }
    return renderCitations(part, startKey + i, cite)
  })
}

/* ---- Components ---- */

export function ChatMessage({ msg, anchorPrefix }: { msg: ChatMsg; anchorPrefix: string }) {
  const isUser = msg.role === 'user'
  const hasMarkdown = !isUser && /[`*]/.test(msg.content)
  const cite: CiteContext | null =
    !isUser && msg.trail?.sources.length
      ? { known: new Set(msg.trail.sources.map((s) => s.id)), anchorPrefix }
      : null

  return (
    <div className={cn('flex gap-3 max-w-3xl', isUser ? 'ms-auto flex-row-reverse' : '')}>
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser ? 'bg-brand-400/20 text-brand-400' : 'bg-surface-700 text-muted-foreground',
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={cn(
          'rounded-xl px-4 py-3 text-sm leading-relaxed',
          isUser
            ? 'bg-brand-400/10 text-foreground border border-brand-400/20'
            : 'bg-card text-foreground border border-border',
        )}
      >
        {msg.agent_key && !isUser && (
          <div className="text-xs text-muted-foreground mb-1 font-medium">{msg.agent_key}</div>
        )}
        {msg.pending && !msg.content ? (
          <TypingDots />
        ) : (
          <div className="whitespace-pre-wrap" dir="auto">
            {hasMarkdown
              ? renderMarkdown(msg.content, cite)
              : renderCitations(msg.content, 0, cite)}
          </div>
        )}
        {!isUser && msg.trail && <TrailPanel trail={msg.trail} anchorPrefix={anchorPrefix} />}
        {msg.timestamp && !msg.pending && (
          <div className="text-xs text-muted-foreground mt-1 opacity-60">
            <bdi>{new Date(msg.timestamp).toLocaleTimeString()}</bdi>
          </div>
        )}
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <div className="flex gap-1 py-1" aria-label="Preparing the answer">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}
