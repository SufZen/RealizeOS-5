import { useId, type ReactNode } from 'react'

/** On/off for a setting that applies immediately. For choices that need saving, use a checkbox. */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled,
}: {
  checked: boolean
  onChange: (next: boolean) => void
  label: ReactNode
  description?: ReactNode
  disabled?: boolean
}) {
  const id = useId()
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="grid gap-0.5">
        <label htmlFor={id} className="rz-label cursor-pointer">
          {label}
        </label>
        {description && <span className="rz-help">{description}</span>}
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className="rz-switch mt-0.5 disabled:opacity-50"
      />
    </div>
  )
}
