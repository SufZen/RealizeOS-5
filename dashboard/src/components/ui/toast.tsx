import { useState, useCallback, createContext, useContext, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type ToastType = 'success' | 'error' | 'info' | 'warning'

interface Toast {
  id: string
  type: ToastType
  message: string
  duration?: number
}

interface ToastCtx {
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
  warning: (message: string) => void
}

const TOAST_META: Record<ToastType, { icon: typeof Info; color: string; bg: string }> = {
  success: { icon: CheckCircle2, color: 'text-green-400', bg: 'border-green-400/20 bg-green-400/5' },
  error:   { icon: AlertCircle,  color: 'text-red-400',   bg: 'border-red-400/20 bg-red-400/5' },
  info:    { icon: Info,         color: 'text-blue-400',  bg: 'border-blue-400/20 bg-blue-400/5' },
  warning: { icon: AlertTriangle, color: 'text-amber-400', bg: 'border-amber-400/20 bg-amber-400/5' },
}

/* ------------------------------------------------------------------ */
/* Context                                                             */
/* ------------------------------------------------------------------ */

const ToastContext = createContext<ToastCtx>({
  success: () => {},
  error: () => {},
  info: () => {},
  warning: () => {},
})

export const useToast = () => useContext(ToastContext)

/* ------------------------------------------------------------------ */
/* Provider                                                            */
/* ------------------------------------------------------------------ */

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((type: ToastType, message: string, duration = 4000) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`
    setToasts((prev) => [...prev, { id, type, message, duration }])
    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id))
      }, duration)
    }
  }, [])

  const remove = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const ctx: ToastCtx = {
    success: (msg) => addToast('success', msg),
    error:   (msg) => addToast('error', msg),
    info:    (msg) => addToast('info', msg),
    warning: (msg) => addToast('warning', msg),
  }

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      {toasts.length > 0 &&
        createPortal(
          <div className="fixed bottom-4 right-4 z-[10001] flex flex-col gap-2 w-80">
            {toasts.map((toast) => {
              const meta = TOAST_META[toast.type]
              const Icon = meta.icon
              return (
                <div
                  key={toast.id}
                  className={cn(
                    'flex items-start gap-3 rounded-xl border p-4 shadow-lg animate-in slide-in-from-right-full',
                    meta.bg,
                    'bg-card',
                  )}
                >
                  <Icon className={cn('h-5 w-5 shrink-0 mt-0.5', meta.color)} />
                  <p className="text-sm text-foreground flex-1">{toast.message}</p>
                  <button
                    onClick={() => remove(toast.id)}
                    className="p-0.5 rounded text-muted-foreground hover:text-foreground transition-colors shrink-0"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )
            })}
          </div>,
          document.body,
        )}
    </ToastContext.Provider>
  )
}
