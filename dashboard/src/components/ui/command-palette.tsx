import { useEffect, useMemo, useRef, useState, type ComponentType, type ReactNode } from 'react'
import { CornerDownLeft, Search } from 'lucide-react'
import { Kbd } from '@/components/ui/badge'

export interface Command {
  id: string
  label: string
  group: string
  icon?: ComponentType<{ className?: string }>
  hint?: ReactNode
  /** Extra words to match, e.g. Hebrew names or synonyms. */
  keywords?: string
  run: () => void
}

function score(cmd: Command, q: string): number {
  if (!q) return 1
  const hay = `${cmd.label} ${cmd.keywords ?? ''} ${cmd.group}`.toLowerCase()
  const needle = q.toLowerCase().trim()
  if (cmd.label.toLowerCase().startsWith(needle)) return 3
  if (hay.includes(needle)) return 2
  // loose subsequence match: "apr" finds "Approvals"
  let i = 0
  for (const ch of hay) if (ch === needle[i]) i++
  return i === needle.length ? 1 : 0
}

/**
 * ⌘K / Ctrl+K: go anywhere, do anything, without the mouse. Built on the
 * native <dialog> so focus and Escape come for free.
 */
export function CommandPalette({
  commands,
  open,
  onOpenChange,
  placeholder = 'Search pages and actions',
}: {
  commands: Command[]
  open: boolean
  onOpenChange: (open: boolean) => void
  placeholder?: string
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)

  // Global shortcut
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        onOpenChange(!open)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onOpenChange])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) {
      el.showModal()
      // React's autoFocus runs on mount, before the dialog opens
      inputRef.current?.focus()
    }
    if (!open && el.open) el.close()
  }, [open])

  const results = useMemo(
    () =>
      commands
        .map((c) => ({ c, s: score(c, query) }))
        .filter((r) => r.s > 0)
        .sort((a, b) => b.s - a.s)
        .map((r) => r.c),
    [commands, query],
  )

  const groups = useMemo(() => {
    const map = new Map<string, Command[]>()
    for (const c of results) map.set(c.group, [...(map.get(c.group) ?? []), c])
    return [...map.entries()]
  }, [results])

  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: 'nearest' })
  }, [active])

  function run(cmd: Command | undefined) {
    if (!cmd) return
    onOpenChange(false)
    cmd.run()
  }

  let index = -1
  return (
    <dialog
      ref={ref}
      className="rz-palette rz-dialog"
      aria-label="Command palette"
      onClose={() => {
        // Start fresh next time it opens
        setQuery('')
        setActive(0)
        onOpenChange(false)
      }}
      onClick={(e) => e.target === e.currentTarget && onOpenChange(false)}
    >
      <div className="relative">
        <Search
          className="absolute top-1/2 -translate-y-1/2 start-4 h-[18px] w-[18px] text-subtle-foreground"
          aria-hidden
        />
        <input
          className="rz-palette__input"
          ref={inputRef}
          value={query}
          placeholder={placeholder}
          role="combobox"
          aria-expanded="true"
          aria-controls="rz-palette-list"
          aria-activedescendant={results[active] ? `cmd-${results[active].id}` : undefined}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(a + 1, results.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(a - 1, 0))
            } else if (e.key === 'Enter') {
              e.preventDefault()
              run(results[active])
            }
          }}
        />
      </div>
      <div ref={listRef} id="rz-palette-list" role="listbox" className="rz-palette__list">
        {results.length === 0 && (
          <p className="px-3 py-8 text-center text-sm text-muted-foreground">
            Nothing matches “{query}”. Try a page name like Approvals.
          </p>
        )}
        {groups.map(([group, cmds]) => (
          <div key={group} role="group" aria-label={group}>
            <div className="rz-palette__group">{group}</div>
            {cmds.map((c) => {
              index += 1
              const i = index
              const Icon = c.icon
              return (
                <div
                  key={c.id}
                  id={`cmd-${c.id}`}
                  role="option"
                  aria-selected={i === active}
                  className="rz-palette__item"
                  onMouseMove={() => setActive(i)}
                  onClick={() => run(c)}
                >
                  {Icon && <Icon />}
                  <span>{c.label}</span>
                  {c.hint && <span className="rz-palette__hint">{c.hint}</span>}
                </div>
              )
            })}
          </div>
        ))}
      </div>
      <div className="rz-palette__foot" aria-hidden>
        <span>
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd> to move
        </span>
        <span>
          <Kbd>
            <CornerDownLeft className="h-2.5 w-2.5" />
          </Kbd>{' '}
          to open
        </span>
        <span>
          <Kbd>Esc</Kbd> to close
        </span>
      </div>
    </dialog>
  )
}
