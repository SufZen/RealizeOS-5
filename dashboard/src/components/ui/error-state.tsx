import { AlertCircle, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ErrorStateProps {
  message?: string
  onRetry?: () => void
  className?: string
}

export function ErrorState({ message = 'Something went wrong', onRetry, className }: ErrorStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center h-64 gap-3', className)}>
      <AlertCircle className="h-8 w-8 text-red-400" />
      <p className="text-sm text-red-400 text-center max-w-md">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-border text-foreground hover:bg-surface-700 transition-colors"
          aria-label="Try again"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Try again
        </button>
      )}
    </div>
  )
}
