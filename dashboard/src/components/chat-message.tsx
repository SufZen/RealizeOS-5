import { Bot, User } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  agent_key?: string
  timestamp?: string
}

/* ---- Lightweight markdown rendering ---- */

function renderMarkdown(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g
  let lastIndex = 0
  let key = 0

  // First pass: split by code blocks
  let match: RegExpExecArray | null
  while ((match = codeBlockRegex.exec(text)) !== null) {
    // Add text before the code block
    if (match.index > lastIndex) {
      nodes.push(...renderInline(text.slice(lastIndex, match.index), key))
      key += 100
    }
    // Add the code block
    const lang = match[1] || 'plain'
    nodes.push(
      <pre
        key={`code-${key++}`}
        className="bg-surface-800 border border-border rounded-lg p-3 text-xs font-mono overflow-x-auto my-2"
      >
        <div className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">{lang}</div>
        <code>{match[2]}</code>
      </pre>
    )
    lastIndex = match.index + match[0].length
  }

  // Add remaining text after last code block
  if (lastIndex < text.length) {
    nodes.push(...renderInline(text.slice(lastIndex), key))
  }

  return nodes
}

function renderInline(text: string, startKey: number): React.ReactNode[] {
  if (!text) return []

  // Split by inline patterns: **bold**, *italic*, `inline code`
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/)

  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={startKey + i} className="font-semibold">{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('*') && part.endsWith('*') && !part.startsWith('**')) {
      return <em key={startKey + i}>{part.slice(1, -1)}</em>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return (
        <code key={startKey + i} className="bg-surface-800 px-1.5 py-0.5 rounded text-xs font-mono text-brand-400">
          {part.slice(1, -1)}
        </code>
      )
    }
    return <span key={startKey + i}>{part}</span>
  })
}

/* ---- Components ---- */

export function ChatMessage({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === 'user'
  const hasMarkdown = !isUser && /[`*]/.test(msg.content)

  return (
    <div className={cn('flex gap-3 max-w-3xl', isUser ? 'ml-auto flex-row-reverse' : '')}>
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
        <div className="whitespace-pre-wrap">
          {hasMarkdown ? renderMarkdown(msg.content) : msg.content}
        </div>
        {msg.timestamp && (
          <div className="text-xs text-muted-foreground mt-1 opacity-60">
            {new Date(msg.timestamp).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  )
}

export function TypingIndicator() {
  return (
    <div className="flex gap-3 max-w-3xl">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-700 text-muted-foreground">
        <Bot className="h-4 w-4" />
      </div>
      <div className="rounded-xl px-4 py-3 bg-card border border-border">
        <div className="flex gap-1">
          <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  )
}
