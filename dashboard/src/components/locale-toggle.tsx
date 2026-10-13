import { Languages } from 'lucide-react'
import { useLocale } from './locale-provider'
import { cn } from '@/lib/utils'
import type { LocaleOverride } from '@/lib/locale'

const CYCLE: LocaleOverride[] = ['auto', 'he', 'en']

const LABEL: Record<LocaleOverride, string> = {
  auto: 'Language: venture',
  he: 'Language: עברית',
  en: 'Language: English',
}

/** Cycles the text direction: follow the venture's locale, Hebrew (RTL) or English (LTR). */
export function LocaleToggle() {
  const { override, setOverride } = useLocale()
  const next = CYCLE[(CYCLE.indexOf(override) + 1) % CYCLE.length]!

  return (
    <button
      onClick={() => setOverride(next)}
      className={cn(
        'flex items-center gap-2.5 w-full h-8 rounded-[5px] px-2.5 text-[13px]',
        'text-muted-foreground hover:text-foreground hover:bg-surface-700/60',
        'transition-colors',
      )}
      title={`${LABEL[override]} — click for ${LABEL[next]}`}
    >
      <Languages className="h-4 w-4" />
      <span>{LABEL[override]}</span>
    </button>
  )
}
