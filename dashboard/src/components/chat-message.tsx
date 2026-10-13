import { Bot } from 'lucide-react'
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
          <button
            key={i}
            type="button"
            onClick={() =>
              document
                .getElementById(target)
                ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
            }
            className="rz-source"
            aria-label={`Source ${part.marker}`}
          >
            {part.marker}
          </button>
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
      <pre key={`code-${key++}`} className="rz-code my-2 whitespace-pre">
        <div className="mb-1 text-[11px] text-subtle-foreground">{lang}</div>
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
        <code key={startKey + i} className="font-mono text-[0.9em]">
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
    <div
      className={cn(
        'flex gap-3 max-w-3xl rz-enter-scale',
        isUser ? 'ms-auto flex-row-reverse' : '',
      )}
    >
      {isUser ? (
        <span className="rz-avatar mt-0.5" aria-hidden>
          You
        </span>
      ) : (
        <span className="rz-avatar rz-avatar--agent mt-0.5" aria-hidden>
          <Bot className="h-3.5 w-3.5" />
        </span>
      )}
      <div
        className={cn(
          'min-w-0 rounded-[10px] px-4 py-3 text-[15px] leading-relaxed text-foreground',
          isUser
            ? 'bg-surface-700 rounded-se-[3px]'
            : 'border border-border bg-card rounded-ss-[3px]',
        )}
      >
        {msg.agent_key && !isUser && (
          <div className="mb-1 text-xs font-medium text-violet-400">{msg.agent_key}</div>
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
          <div className="mt-1.5 text-xs tabular text-subtle-foreground">
            <bdi>{new Date(msg.timestamp).toLocaleTimeString()}</bdi>
          </div>
        )}
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <div
      className="flex items-center gap-1.5 py-1.5"
      role="status"
      aria-label="Preparing the answer"
    >
      {[0, 200, 400].map((delay) => (
        <span
          key={delay}
          className="h-1.5 w-1.5 rounded-full bg-violet-400 animate-pulse"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}
