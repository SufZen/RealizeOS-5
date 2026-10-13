/**
 * Words on the agent pages that aren't gates (those are in `permissions.ts`),
 * in English and Hebrew; anything that isn't Hebrew reads English.
 */
import { baseLanguage } from '@/lib/locale'

/** The toast when a pause or resume fails and the server gave no reason. */
export function agentChangeFailed(
  verb: 'pause' | 'resume',
  language: string | null | undefined,
): string {
  if (baseLanguage(language) === 'he') {
    return verb === 'pause' ? 'לא ניתן היה להשהות את הסוכן' : 'לא ניתן היה לחדש את הסוכן'
  }
  return `Couldn’t ${verb} the agent`
}
