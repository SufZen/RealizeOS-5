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

/**
 * The `Intl` locale for dates and times in a language: Hebrew reads Hebrew,
 * anything else English (the languages the dashboard speaks).
 */
export function intlLocale(language: string | undefined | null): 'he' | 'en' {
  return baseLanguage(language) === 'he' ? 'he' : 'en'
}

/** A date and time in the person's language; the input as is when it isn't a date. */
export function formatDateTime(iso: string, language: string | undefined | null): string {
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return iso
  return t.toLocaleString(intlLocale(language), { dateStyle: 'medium', timeStyle: 'short' })
}

/**
 * The language before anyone signs in (no venture yet): the person's saved
 * choice, else the browser's language.
 */
export function signedOutLanguage(
  override: LocaleOverride,
  browserLanguage: string | undefined | null,
): string {
  return override === 'auto' ? baseLanguage(browserLanguage) : override
}
