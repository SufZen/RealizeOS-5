/**
 * Language and text direction for the dashboard (STORY-19).
 *
 * The active venture's `locale` decides the page direction (Hebrew → RTL);
 * a person can override it. UI labels stay English for now; the content
 * (answers, documents, approvals) is what turns right-to-left.
 */

/** Languages written right-to-left. */
const RTL_LANGUAGES = new Set(['he', 'ar', 'fa', 'ur', 'yi'])

export type Direction = 'ltr' | 'rtl'
/** A person's choice: follow the venture, or force a language. */
export type LocaleOverride = 'auto' | 'he' | 'en'

/** Base language of a locale tag: "he-IL" → "he". */
export function baseLanguage(locale: string | undefined | null): string {
  return (locale || '').trim().toLowerCase().split(/[-_]/)[0] || 'en'
}

export function directionFor(locale: string | undefined | null): Direction {
  return RTL_LANGUAGES.has(baseLanguage(locale)) ? 'rtl' : 'ltr'
}

/** The language in effect: the override, or the venture's locale, or English. */
export function resolveLanguage(
  override: LocaleOverride,
  ventureLocale: string | undefined | null,
): string {
  return override === 'auto' ? baseLanguage(ventureLocale) : override
}
