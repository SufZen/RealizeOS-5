import { Sun, Moon, Monitor } from 'lucide-react'
import { useTheme } from './theme-provider'
import { cn } from '@/lib/utils'

const CYCLE: Array<'dark' | 'light' | 'system'> = ['dark', 'light', 'system']

const META = {
  dark: { icon: Moon, label: 'Dark' },
  light: { icon: Sun, label: 'Light' },
  system: { icon: Monitor, label: 'System' },
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const next = CYCLE[(CYCLE.indexOf(theme) + 1) % CYCLE.length]!
  const { icon: Icon, label } = META[theme]

  return (
    <button
      onClick={() => setTheme(next)}
      className={cn(
        'flex items-center gap-2.5 w-full h-8 rounded-[5px] px-2.5 text-[13px]',
        'text-muted-foreground hover:text-foreground hover:bg-surface-700/60',
        'transition-colors',
      )}
      title={`Theme: ${label} — click for ${META[next].label}`}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
    </button>
  )
}
