import { forwardRef, type ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'approve'
export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Shows a scan line and blocks clicks while keeping the label in place. */
  busy?: boolean
  block?: boolean
}

/** The one button. One `primary` per view; everything else is secondary or ghost. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', busy, block, className, disabled, type, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      aria-busy={busy || undefined}
      disabled={disabled || busy}
      className={cn(
        'rz-btn',
        `rz-btn--${variant}`,
        size !== 'md' && `rz-btn--${size}`,
        block && 'rz-btn--block',
        className,
      )}
      {...props}
    />
  )
})

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required: an icon button has no visible text, so this is its name and tooltip. */
  label: string
  size?: 'sm' | 'md'
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, size = 'md', className, type, ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type ?? 'button'}
      aria-label={label}
      data-tip={label}
      className={cn('rz-icon-btn', size === 'sm' && 'rz-icon-btn--sm', className)}
      {...props}
    />
  )
})
