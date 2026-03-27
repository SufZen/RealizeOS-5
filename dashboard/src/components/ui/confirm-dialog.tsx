import { useEffect } from 'react'
import type { ReactNode } from 'react'
import { AlertCircle, Trash2 } from 'lucide-react'

interface ConfirmDialogProps {
  isOpen: boolean
  title: string
  message: ReactNode
  confirmText?: string
  cancelText?: string
  isDestructive?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  isDestructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    if (isOpen) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [isOpen, onCancel])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div 
        className="fixed inset-0 bg-background/80 backdrop-blur-sm transition-opacity" 
        onClick={onCancel}
      />
      <div className="relative z-50 grid w-full max-w-lg gap-4 rounded-xl border border-border bg-card p-6 shadow-lg shadow-black/5 animate-in fade-in zoom-in-95 duration-200">
        <div className="flex flex-col space-y-2 text-center sm:text-left">
          <h2 className="text-lg font-semibold leading-none tracking-tight flex items-center gap-2">
            {isDestructive && <AlertCircle className="h-5 w-5 text-red-500" />}
            {title}
          </h2>
          <div className="text-sm text-muted-foreground">{message}</div>
        </div>
        
        <div className="flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2 mt-4">
          <button
            onClick={onCancel}
            className="mt-2 sm:mt-0 inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none hover:bg-muted bg-transparent border border-border h-10 py-2 px-4 text-foreground"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            className={`inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:opacity-50 disabled:pointer-events-none h-10 py-2 px-4 shadow-sm ${
              isDestructive
                ? 'bg-red-500 text-white hover:bg-red-600'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            }`}
          >
            {isDestructive && <Trash2 className="mr-2 h-4 w-4" />}
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}
