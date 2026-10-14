/**
 * Words on the LLM routing settings and the "notice" line in the chat
 * trail, in English and Hebrew. The language comes from the locale mechanism
 * (`useLocale().language`); anything that isn't Hebrew reads English. Model
 * ids and provider names are data and stay left to right.
 */
import { baseLanguage } from '@/lib/locale'
import type { Tier } from '@/lib/llm-routing'

export interface LlmSettingsText {
  title: string
  subtitle: string
  primaryLabel: string
  primaryHelp: string
  /** The "no explicit choice" option: the first provider that answers. */
  primaryAuto: string
  /** Shown beside a provider that is the choice but cannot answer now. */
  notAvailable: string
  tiersTitle: string
  tierLabel: Record<Tier, string>
  tierHelp: Record<Tier, string>
  /** Placeholder when the tier is unset: the model used by default. */
  tierDefault: (model: string | null) => string
  modelPlaceholder: string
  fallbackLabel: string
  fallbackHelp: string
  fallbackPlaceholder: string
  save: string
  saving: string
  saved: string
  nothingToSave: string
  saveError: (detail: string) => string
  rulesTitle: string
  deadTitle: string
  deadLine: (model: string, provider: string) => string
  usageTitle: string
}

const EN: LlmSettingsText = {
  title: 'LLM Routing',
  subtitle: 'Choose the main provider and the model for each kind of task. Changes apply at once.',
  primaryLabel: 'Primary provider',
  primaryHelp: 'Tried first. If it fails, the fallback order below is used.',
  primaryAuto: 'Automatic (first available)',
  notAvailable: 'not available',
  tiersTitle: 'Model for each tier',
  tierLabel: { fast: 'Fast', standard: 'Standard', deep: 'Deep' },
  tierHelp: {
    fast: 'Quick answers and simple tasks',
    standard: 'Writing and analysis',
    deep: 'Strategy and multi-step reasoning',
  },
  tierDefault: (model) => (model ? `Default: ${model}` : 'Default'),
  modelPlaceholder: 'provider/model-name',
  fallbackLabel: 'Fallback order',
  fallbackHelp: 'Provider names separated by commas, for example gemini, claude, openai',
  fallbackPlaceholder: 'gemini, claude',
  save: 'Save routing',
  saving: 'Saving…',
  saved: 'Saved',
  nothingToSave: 'No changes',
  saveError: (detail) =>
    detail ? `Couldn’t save: ${detail}` : 'Couldn’t save the routing settings. Try again.',
  rulesTitle: 'How tasks are routed',
  deadTitle: 'Some configured models are not answering',
  deadLine: (model, provider) =>
    `${model} (${provider}) returned “not found”. It is probably retired. Choose another model above.`,
  usageTitle: 'Usage Stats',
}

const HE: LlmSettingsText = {
  title: 'ניתוב מודלים',
  subtitle: 'בוחרים את הספק הראשי ואת המודל לכל סוג משימה. השינויים נכנסים לתוקף מיד.',
  primaryLabel: 'ספק ראשי',
  primaryHelp: 'מנסים אותו ראשון. אם הוא נכשל, עוברים לפי סדר הגיבוי שלמטה.',
  primaryAuto: 'אוטומטי (הראשון הזמין)',
  notAvailable: 'לא זמין',
  tiersTitle: 'מודל לכל רמה',
  tierLabel: { fast: 'מהיר', standard: 'רגיל', deep: 'עמוק' },
  tierHelp: {
    fast: 'תשובות קצרות ומשימות פשוטות',
    standard: 'כתיבה וניתוח',
    deep: 'אסטרטגיה וחשיבה רב־שלבית',
  },
  tierDefault: (model) => (model ? `ברירת מחדל: ${model}` : 'ברירת מחדל'),
  modelPlaceholder: 'provider/model-name',
  fallbackLabel: 'סדר גיבוי',
  fallbackHelp: 'שמות ספקים מופרדים בפסיקים, למשל gemini, claude, openai',
  fallbackPlaceholder: 'gemini, claude',
  save: 'שמירת הניתוב',
  saving: 'שומר…',
  saved: 'נשמר',
  nothingToSave: 'אין שינויים',
  saveError: (detail) =>
    detail ? `השמירה נכשלה: ${detail}` : 'שמירת הגדרות הניתוב נכשלה. כדאי לנסות שוב.',
  rulesTitle: 'איך משימות מנותבות',
  deadTitle: 'חלק מהמודלים שהוגדרו לא עונים',
  deadLine: (model, provider) =>
    `${model} (${provider}) החזיר “לא נמצא”. כנראה שהוא הוצא משימוש. כדאי לבחור מודל אחר למעלה.`,
  usageTitle: 'נתוני שימוש',
}

export function llmSettingsText(language: string | null | undefined): LlmSettingsText {
  return baseLanguage(language) === 'he' ? HE : EN
}

/** The trail's warning lines (`notice` events), keyed by the server's `code`. */
export interface NoticeText {
  byCode: Record<string, string>
  /** Shown when the code is unknown and the server sent no message. */
  generic: string
}

const NOTICE: Record<'en' | 'he', NoticeText> = {
  en: {
    byCode: {
      tools_unavailable: 'This model can’t use tools here, so the answer was written without them.',
      tools_error: 'A tool call failed, so the answer may be missing something.',
    },
    generic: 'Something limited this answer.',
  },
  he: {
    byCode: {
      tools_unavailable: 'המודל הזה לא יכול להשתמש כאן בכלים, ולכן התשובה נכתבה בלעדיהם.',
      tools_error: 'קריאה לכלי נכשלה, ולכן ייתכן שחסר משהו בתשובה.',
    },
    generic: 'משהו הגביל את התשובה הזאת.',
  },
}

/** The line for a notice: our words for a known code, else the server's message. */
export function noticeLine(
  notice: { code?: string; message?: string },
  language: string | null | undefined,
): string {
  const words = NOTICE[baseLanguage(language) === 'he' ? 'he' : 'en']
  return (notice.code && words.byCode[notice.code]) || notice.message?.trim() || words.generic
}
