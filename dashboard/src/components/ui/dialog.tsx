import { useEffect, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * A modal built on the native <dialog>: focus trapping, Escape and the top
 * layer come from the browser. Opening and closing both animate in CSS.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  className,
}: {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  footer?: ReactNode
  className?: string
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) el.showModal()
    if (!open && el.open) el.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className={cn('rz-dialog', className)}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        // A click on the backdrop lands on the <dialog> itself
        if (e.target === e.currentTarget) onClose()
      }}
      aria-labelledby="rz-dialog-title"
    >
      <div className="rz-dialog__head">
        <h2 id="rz-dialog-title" className="rz-dialog__title">
          {title}
        </h2>
      </div>
      <div className="rz-dialog__body">{children}</div>
      {footer && <div className="rz-dialog__foot">{footer}</div>}
    </dialog>
  )
}
