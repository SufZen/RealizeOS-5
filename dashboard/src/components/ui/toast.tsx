/* eslint-disable react-refresh/only-export-components */
import {
  useState,
  useCallback,
  useLayoutEffect,
  useRef,
  createContext,
  useContext,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from 'lucide-react'

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

const TOAST_META: Record<ToastType, { icon: typeof Info; color: string }> = {
  success: { icon: CheckCircle2, color: 'text-success' },
  error: { icon: AlertCircle, color: 'text-danger' },
  info: { icon: Info, color: 'text-info' },
  warning: { icon: AlertTriangle, color: 'text-warning' },
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
/* Region                                                              */
/* ------------------------------------------------------------------ */

/**
 * A manual popover, so toasts live in the browser's top layer and stay above
 * an open modal <dialog>. The top layer stacks by most recently shown, so
 * the region re-enters it whenever a toast arrives.
 */
function ToastRegion({ count, children }: { count: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || typeof el.showPopover !== 'function') return
    if (el.matches(':popover-open')) el.hidePopover()
    el.showPopover()
  }, [count])
  return (
    <div ref={ref} popover="manual" className="rz-toast-region" role="status" aria-live="polite">
      {children}
    </div>
  )
}

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
    error: (msg) => addToast('error', msg),
    info: (msg) => addToast('info', msg),
    warning: (msg) => addToast('warning', msg),
  }

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      {toasts.length > 0 &&
        createPortal(
          <ToastRegion count={toasts.length}>
            {toasts.map((toast) => {
              const meta = TOAST_META[toast.type]
              const Icon = meta.icon
              return (
                <div key={toast.id} className="rz-toast">
                  <Icon className={meta.color} aria-hidden />
                  <p className="m-0 flex-1">{toast.message}</p>
                  <button
                    onClick={() => remove(toast.id)}
                    aria-label="Dismiss"
                    className="rz-icon-btn rz-icon-btn--sm -my-1 -me-1"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              )
            })}
          </ToastRegion>,
          document.body,
        )}
    </ToastContext.Provider>
  )
}
