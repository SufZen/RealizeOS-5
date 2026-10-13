/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useVenture } from '@/hooks/use-venture'
import { directionFor, resolveLanguage, type Direction, type LocaleOverride } from '@/lib/locale'

interface LocaleCtx {
  /** Language in effect ("he", "en", ...). */
  language: string
  dir: Direction
  override: LocaleOverride
  setOverride: (o: LocaleOverride) => void
}

const LocaleContext = createContext<LocaleCtx>({
  language: 'en',
  dir: 'ltr',
  override: 'auto',
  setOverride: () => {},
})

export const useLocale = () => useContext(LocaleContext)

const STORAGE_KEY = 'realizeos_locale'

/** The language the person chose in this browser ('auto' when they didn't, or storage is off). */
export function readOverride(): LocaleOverride {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored === 'he' || stored === 'en' ? stored : 'auto'
  } catch {
    return 'auto'
  }
}

/**
 * Sets `<html lang dir>` from the selected venture's locale (Hebrew → RTL),
 * unless the person chose a language. Must sit inside `VentureProvider`.
 */
export function LocaleProvider({ children }: { children: ReactNode }) {
  const { ventures, selected } = useVenture()
  const [override, setOverrideState] = useState<LocaleOverride>(readOverride)

  const ventureLocale = ventures.find((v) => v.key === selected)?.locale
  const language = resolveLanguage(override, ventureLocale)
  const dir = directionFor(language)

  useEffect(() => {
    const root = document.documentElement
    root.lang = language
    root.dir = dir
  }, [language, dir])

  // Leaving the signed-in area (sign-out) returns the page to English LTR.
  useEffect(
    () => () => {
      document.documentElement.lang = 'en'
      document.documentElement.dir = 'ltr'
    },
    [],
  )

  function setOverride(o: LocaleOverride) {
    setOverrideState(o)
    try {
      localStorage.setItem(STORAGE_KEY, o)
    } catch {
      // localStorage unavailable: the choice lasts for this page only
    }
  }

  return (
    <LocaleContext.Provider value={{ language, dir, override, setOverride }}>
      {children}
    </LocaleContext.Provider>
  )
}
