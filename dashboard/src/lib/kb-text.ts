/**
 * Words in the knowledge-base browser that sit next to its read-only gate, in
 * English and Hebrew; anything that isn't Hebrew reads English.
 */
import { baseLanguage } from '@/lib/locale'

/** What to do when no file is open: view only, or view and edit. */
export function kbEmptyHint(readOnly: boolean, language: string | null | undefined): string {
  if (baseLanguage(language) === 'he') {
    return readOnly
      ? 'בחרו קובץ לצפייה, או חפשו בבסיס הידע'
      : 'בחרו קובץ לצפייה או לעריכה, או חפשו בבסיס הידע'
  }
  return readOnly
    ? 'Select a file to view, or search the knowledge base'
    : 'Select a file to view or edit, or search the knowledge base'
}
