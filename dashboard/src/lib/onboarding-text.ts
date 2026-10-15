/**
 * Words in the onboarding wizard, in English and Hebrew. The language comes
 * from the locale mechanism (`useLocale().language`: the person's choice, or
 * the venture's locale); anything that isn't Hebrew reads English. Provider
 * names, URLs and keys are data and stay as they are, left to right.
 */
import { baseLanguage, type Direction, type LocaleOverride } from '@/lib/locale'

export type ProviderId = 'anthropic' | 'google_ai' | 'openai' | 'ollama' | 'litellm'

interface Line {
  title: string
  description: string
}

export interface OnboardingText {
  lang: string
  dir: Direction
  /** The other language: what the wizard's language button switches to. */
  switchTarget: Exclude<LocaleOverride, 'auto'>
  /** The button's visible text, in the other language. */
  switchTo: string
  /** The button's accessible name. */
  switchLabel: string
  loading: string
  setup: string
  stepOf: (step: number, total: number) => string
  progressLabel: string
  progressText: (step: number, total: number) => string
  welcomeTitle: string
  welcomeDescription: string
  /** Multi-agent, trust ladder, routing, tools: in that order. */
  features: [Line, Line, Line, Line]
  connectTitle: string
  connectDescription: string
  providers: Record<ProviderId, { description: string; help: string }>
  connected: string
  serverUrl: string
  /** LiteLLM's model field and its optional gateway URL. */
  modelId: string
  apiBaseOptional: string
  /** The primary-provider choice inside the connect step. */
  primaryTitle: string
  primaryHelp: string
  primaryAuto: string
  primarySaved: string
  primaryError: (detail: string) => string
  apiKey: string
  showKey: string
  hideKey: string
  connect: string
  saveError: (detail: string) => string
  doneTitle: string
  /** "RealizeOS is ready… You’ve connected" · count · ". You can add more…" */
  doneBefore: string
  providerCount: (count: number) => string
  doneAfter: string
  connectedProvider: (name: string) => string
  nextTitle: string
  /** Chat, ventures, settings: in that order. */
  nextSteps: [Line, Line, Line]
  trailLabel: string
  getStarted: string
  back: string
  continue: string
  needProvider: string
  finish: string
  /** For someone who can't connect providers, on a server that has none yet. */
  providerNeededTitle: string
  providerNeeded: string
  dismiss: string
}

const EN: OnboardingText = {
  lang: 'en',
  dir: 'ltr',
  switchTarget: 'he',
  switchTo: 'עברית',
  switchLabel: 'Switch to Hebrew (עברית)',
  loading: 'Loading setup',
  setup: 'Setup',
  stepOf: (step, total) => `${step} of ${total}`,
  progressLabel: 'Setup progress',
  progressText: (step, total) => `Step ${step} of ${total}`,
  welcomeTitle: 'Welcome to RealizeOS',
  welcomeDescription:
    'Your AI-powered operating system for business. Let’s get you set up in under 2 minutes.',
  features: [
    {
      title: 'Multi-agent system',
      description: 'Deploy specialized AI agents for different tasks',
    },
    {
      title: 'Trust ladder',
      description: 'Control what agents can do autonomously vs. with approval',
    },
    {
      title: 'Smart routing',
      description: 'Automatically route tasks to the best model for the job',
    },
    {
      title: 'Tools and integrations',
      description: 'Web search, browser automation, Google Workspace, and more',
    },
  ],
  connectTitle: 'Connect an AI provider',
  connectDescription:
    'RealizeOS needs at least one LLM provider to power your agents. Connect one or more below.',
  providers: {
    anthropic: {
      description: 'Best for complex reasoning, writing, and code',
      help: 'Get your key at console.anthropic.com',
    },
    google_ai: {
      description: 'Fast and cost-effective for most tasks',
      help: 'Get your key at aistudio.google.com',
    },
    openai: {
      description: 'Strong general-purpose AI models',
      help: 'Get your key at platform.openai.com',
    },
    ollama: {
      description: 'Run models locally — free, private, no API key',
      help: 'Default URL: http://localhost:11434',
    },
    litellm: {
      description: 'Any other provider LiteLLM supports: Mistral, Groq, Bedrock, a gateway…',
      help: 'Use the provider/model form, for example mistral/mistral-large-latest. Set that provider’s own key in .env.',
    },
  },
  connected: 'Connected',
  serverUrl: 'Server URL',
  modelId: 'Model',
  apiBaseOptional: 'API base URL (optional)',
  primaryTitle: 'Primary provider',
  primaryHelp: 'Used first for every task. You can change it later in Settings.',
  primaryAuto: 'Automatic (first available)',
  primarySaved: 'Saved',
  primaryError: (detail) =>
    detail ? `Couldn’t save the choice: ${detail}` : 'Couldn’t save the choice. Try again.',
  apiKey: 'API key',
  showKey: 'Show key',
  hideKey: 'Hide key',
  connect: 'Connect',
  saveError: (detail) =>
    detail ? `Couldn’t connect: ${detail}` : 'Couldn’t connect. Check the value and try again.',
  doneTitle: 'You’re all set',
  doneBefore: 'RealizeOS is ready to go. You’ve connected',
  providerCount: (count) => `${count} provider${count !== 1 ? 's' : ''}`,
  doneAfter: '. You can add more integrations anytime from the Setup page.',
  connectedProvider: (name) => `Connected ${name}`,
  nextTitle: 'What to do next',
  nextSteps: [
    { title: 'Start a conversation', description: 'Chat with your AI agents' },
    { title: 'Explore ventures', description: 'See your business units and agents' },
    { title: 'Configure settings', description: 'Adjust features, governance, and trust levels' },
  ],
  trailLabel: 'Setup and next steps',
  getStarted: 'Get started',
  back: 'Back',
  continue: 'Continue',
  needProvider: 'Connect at least one provider to continue',
  finish: 'Go to dashboard',
  providerNeededTitle: 'No AI provider is connected yet',
  providerNeeded:
    'An owner or admin needs to connect an AI provider before your agents can answer. You can look around in the meantime.',
  dismiss: 'Dismiss',
}

const HE: OnboardingText = {
  lang: 'he',
  dir: 'rtl',
  switchTarget: 'en',
  switchTo: 'English',
  switchLabel: 'מעבר לאנגלית (English)',
  loading: 'טוען את ההגדרה',
  setup: 'הגדרה',
  stepOf: (step, total) => `${step} מתוך ${total}`,
  progressLabel: 'התקדמות ההגדרה',
  progressText: (step, total) => `שלב ${step} מתוך ${total}`,
  welcomeTitle: 'ברוכים הבאים ל-RealizeOS',
  welcomeDescription: 'מערכת ההפעלה של העסק, מבוססת AI. נגדיר הכול בפחות משתי דקות.',
  features: [
    { title: 'מערכת מרובת סוכנים', description: 'סוכני AI מתמחים למשימות שונות' },
    { title: 'סולם אמון', description: 'קובעים מה הסוכנים עושים לבד ומה רק באישור' },
    { title: 'ניתוב חכם', description: 'כל משימה עוברת אוטומטית למודל המתאים לה ביותר' },
    {
      title: 'כלים ושילובים',
      description: 'חיפוש ברשת, אוטומציה של דפדפן, Google Workspace ועוד',
    },
  ],
  connectTitle: 'חיבור ספק AI',
  connectDescription:
    'RealizeOS צריך לפחות ספק מודל שפה אחד כדי להפעיל את הסוכנים שלך. אפשר לחבר אחד או יותר כאן.',
  providers: {
    anthropic: {
      description: 'הכי טוב לחשיבה מורכבת, לכתיבה ולקוד',
      help: 'את המפתח מקבלים ב-console.anthropic.com',
    },
    google_ai: {
      description: 'מהיר וחסכוני לרוב המשימות',
      help: 'את המפתח מקבלים ב-aistudio.google.com',
    },
    openai: {
      description: 'מודלים חזקים לשימוש כללי',
      help: 'את המפתח מקבלים ב-platform.openai.com',
    },
    ollama: {
      description: 'מודלים שרצים מקומית: חינם, פרטי, בלי מפתח API',
      help: 'כתובת ברירת המחדל: http://localhost:11434',
    },
    litellm: {
      description: 'כל ספק אחר ש-LiteLLM תומך בו: Mistral, Groq, Bedrock, שער ועוד',
      help: 'כותבים בצורה provider/model, למשל mistral/mistral-large-latest. את המפתח של הספק עצמו מגדירים בקובץ .env.',
    },
  },
  connected: 'מחובר',
  serverUrl: 'כתובת השרת',
  modelId: 'מודל',
  apiBaseOptional: 'כתובת בסיס ל-API (לא חובה)',
  primaryTitle: 'ספק ראשי',
  primaryHelp: 'משמש ראשון לכל משימה. אפשר לשנות בהמשך בהגדרות.',
  primaryAuto: 'אוטומטי (הראשון הזמין)',
  primarySaved: 'נשמר',
  primaryError: (detail) =>
    detail ? `שמירת הבחירה נכשלה: ${detail}` : 'שמירת הבחירה נכשלה. כדאי לנסות שוב.',
  apiKey: 'מפתח API',
  showKey: 'הצגת המפתח',
  hideKey: 'הסתרת המפתח',
  connect: 'חיבור',
  saveError: (detail) =>
    detail ? `החיבור נכשל: ${detail}` : 'החיבור נכשל. כדאי לבדוק את הערך ולנסות שוב.',
  doneTitle: 'הכול מוכן',
  doneBefore: 'RealizeOS מוכן לעבודה. חיברת',
  providerCount: (count) => (count === 1 ? 'ספק אחד' : `${count} ספקים`),
  doneAfter: '. אפשר להוסיף שילובים בכל עת מדף ההגדרה (Setup).',
  connectedProvider: (name) => `${name} חובר`,
  nextTitle: 'מה עכשיו',
  nextSteps: [
    { title: 'התחלת שיחה', description: 'שיחה עם סוכני ה-AI שלך' },
    { title: 'סיור במיזמים', description: 'יחידות העסק והסוכנים שלך' },
    { title: 'הגדרות', description: 'יכולות, בקרה ורמות אמון' },
  ],
  trailLabel: 'ההגדרה והצעדים הבאים',
  getStarted: 'מתחילים',
  back: 'חזרה',
  continue: 'המשך',
  needProvider: 'יש לחבר לפחות ספק אחד כדי להמשיך',
  finish: 'ללוח הבקרה',
  providerNeededTitle: 'עדיין לא חובר ספק AI',
  providerNeeded:
    'בעלים או מנהל צריכים לחבר ספק AI לפני שהסוכנים יוכלו לענות. בינתיים אפשר להסתכל מסביב.',
  dismiss: 'סגירה',
}

/** The onboarding words for a language ("he", "he-IL", ...); English otherwise. */
export function onboardingText(language: string | null | undefined): OnboardingText {
  return baseLanguage(language) === 'he' ? HE : EN
}
