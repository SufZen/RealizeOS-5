/* eslint-disable react-refresh/only-export-components, react-hooks/set-state-in-effect */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

type Theme = 'dark' | 'light' | 'system'

interface ThemeCtx {
  theme: Theme
  resolved: 'dark' | 'light'
  setTheme: (t: Theme) => void
}

const ThemeContext = createContext<ThemeCtx>({
  theme: 'dark',
  resolved: 'dark',
  setTheme: () => {},
})

export const useTheme = () => useContext(ThemeContext)

const STORAGE_KEY = 'realizeos_theme'

function getSystemTheme(): 'dark' | 'light' {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function resolve(theme: Theme): 'dark' | 'light' {
  return theme === 'system' ? getSystemTheme() : theme
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    try {
      return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'dark'
    } catch {
      return 'dark'
    }
  })

  const [resolved, setResolved] = useState<'dark' | 'light'>(() => resolve(theme))

  // Apply to <html> element
  useEffect(() => {
    const r = resolve(theme)
    setResolved(r)
    const root = document.documentElement
    root.classList.toggle('light', r === 'light')
    root.classList.toggle('dark', r === 'dark')
  }, [theme])

  // Listen for system preference changes
  useEffect(() => {
    if (theme !== 'system') return
    const mql = window.matchMedia('(prefers-color-scheme: light)')
    const handler = () => setResolved(getSystemTheme())
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [theme])

  function setTheme(t: Theme) {
    setThemeState(t)
    try {
      localStorage.setItem(STORAGE_KEY, t)
    } catch {
      // localStorage unavailable
    }
  }

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
