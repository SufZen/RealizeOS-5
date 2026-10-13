/**
 * Words in the app shell around every page (the sidebar and the command
 * palette), in English and Hebrew. The language comes from the locale
 * mechanism (`useLocale().language`); anything that isn't Hebrew reads English.
 */
import { LogOut } from 'lucide-react'
import type { Command } from '@/components/ui/command-palette'
import { baseLanguage } from '@/lib/locale'

export interface ShellText {
  /** The button and command that end the session. */
  signOut: string
  /** Tooltip on that button: who is signed in. */
  signedInAs: (user: string) => string
  /** Command palette group for the account. */
  account: string
  /** Words the command palette matches for signing out (both languages). */
  signOutKeywords: string
  /** Accessible name of the nav badge counting held approvals. */
  heldForYou: (count: number) => string
}

const KEYWORDS = 'sign out log out logout exit leave התנתקות התנתק יציאה'

const EN: ShellText = {
  signOut: 'Sign out',
  signedInAs: (user) => `Signed in as ${user}`,
  account: 'Account',
  signOutKeywords: KEYWORDS,
  heldForYou: (count) => `${count} held for you`,
}

const HE: ShellText = {
  signOut: 'התנתקות',
  signedInAs: (user) => `החשבון המחובר: ${user}`,
  account: 'חשבון',
  signOutKeywords: KEYWORDS,
  heldForYou: (count) => (count === 1 ? 'פריט אחד ממתין לך' : `${count} פריטים ממתינים לך`),
}

/** The shell's words for a language ("he", "he-IL", ...); English otherwise. */
export function shellText(language: string | null | undefined): ShellText {
  return baseLanguage(language) === 'he' ? HE : EN
}

/** The command palette's sign-out command (Ctrl/Cmd K → "Sign out"). */
export function signOutCommand(text: ShellText, run: () => void): Command {
  return {
    id: 'sign-out',
    group: text.account,
    label: text.signOut,
    keywords: text.signOutKeywords,
    icon: LogOut,
    run,
  }
}
