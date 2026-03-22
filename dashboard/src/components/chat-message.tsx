import { Bot, User } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
  agent_key?: string
  timestamp?: string
}

export function ChatMessage({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === 'user'

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
        <div className="whitespace-pre-wrap">{msg.content}</div>
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
