/**
 * Words in the guided tour, in English and Hebrew. The language comes from the
 * locale mechanism (`useLocale().language`); anything that isn't Hebrew reads
 * English. Where each step points and which side it opens on live in
 * `tour-provider.tsx`; only the words change with the language.
 */
import { baseLanguage, type Direction } from '@/lib/locale'

export type TourStepId =
  | 'sidebar'
  | 'overview'
  | 'chat'
  | 'ventures'
  | 'skills'
  | 'pipelines'
  | 'workflows'
  | 'activity'
  | 'approvals'
  | 'evolution'
  | 'routing'
  | 'tools'
  | 'integrations'
  | 'setup'
  | 'settings'
  | 'theme'

interface StepWords {
  title: string
  description: string
}

export interface TourText {
  lang: string
  dir: Direction
  stepOf: (step: number, total: number) => string
  close: string
  progress: string
  skip: string
  back: string
  next: string
  finish: string
  steps: Record<TourStepId, StepWords>
}

const EN: TourText = {
  lang: 'en',
  dir: 'ltr',
  stepOf: (step, total) => `Step ${step} of ${total}`,
  close: 'Close tour',
  progress: 'Tour progress',
  skip: 'Skip tour',
  back: 'Back',
  next: 'Next',
  finish: 'Finish',
  steps: {
    sidebar: {
      title: 'Welcome to RealizeOS',
      description:
        'This is your navigation sidebar. It’s organized into five groups: Core, Build, Monitor, FABRIC and Configure. Let’s walk through the first steps of using the system.',
    },
    overview: {
      title: 'Dashboard overview',
      description:
        'Start here. The Overview page gives you a snapshot of all your ventures, agents, and recent activity in one place.',
    },
    chat: {
      title: 'Chat with your AI',
      description:
        'Talk to your AI agents in natural language. Issue commands, ask questions, or delegate tasks — this is your primary interface.',
    },
    ventures: {
      title: 'Manage ventures',
      description:
        'Ventures are your business units or projects. Each venture has its own agents, skills, and knowledge base. Create your first venture here.',
    },
    skills: {
      title: 'Install skills',
      description:
        'Skills are pre-built capabilities for your agents — like email drafting, research, or scheduling. Browse the library and install what you need.',
    },
    pipelines: {
      title: 'Build pipelines',
      description:
        'Chain multiple agents and tools into automated workflows. Pipelines let you build complex multi-step processes visually.',
    },
    workflows: {
      title: 'Create workflows',
      description:
        'Define YAML-based workflow templates that your agents can execute. Great for repeatable business processes.',
    },
    activity: {
      title: 'Monitor activity',
      description:
        'See everything your agents are doing in real-time. Track actions, outputs, and status across all ventures.',
    },
    approvals: {
      title: 'Review approvals',
      description:
        'When agents need human approval for sensitive actions (sending emails, API calls), requests appear here. You stay in control.',
    },
    evolution: {
      title: 'Track evolution',
      description:
        'Monitor how your agents improve over time. See performance metrics, learning patterns, and optimization suggestions.',
    },
    routing: {
      title: 'Configure routing',
      description:
        'Control which AI models handle which tasks. Set up intelligent routing rules based on cost, quality, or speed preferences.',
    },
    tools: {
      title: 'Manage tools',
      description:
        'Tools are integrations your agents can use — web search, browser, file management, and more. Enable or disable them here.',
    },
    integrations: {
      title: 'Connect integrations',
      description:
        'Link external services like Google Workspace, Slack, Stripe, and more. These let your agents interact with your business tools.',
    },
    setup: {
      title: 'Set up connections',
      description:
        'Configure your AI provider API keys (OpenAI, Anthropic, Google) and other connection settings. This is essential to get started.',
    },
    settings: {
      title: 'System settings',
      description:
        'Fine-tune system features like approval gates, heartbeats, auto-memory, and proactive mode. You can also manage databases and providers.',
    },
    theme: {
      title: 'Language and theme',
      description:
        'Switch between Dark, Light, or System theme, and between English and Hebrew. Your preference is saved automatically. Enjoy using RealizeOS!',
    },
  },
}

const HE: TourText = {
  lang: 'he',
  dir: 'rtl',
  stepOf: (step, total) => `שלב ${step} מתוך ${total}`,
  close: 'סגירת הסיור',
  progress: 'התקדמות הסיור',
  skip: 'דילוג על הסיור',
  back: 'הקודם',
  next: 'הבא',
  finish: 'סיום',
  steps: {
    sidebar: {
      title: 'ברוכים הבאים ל-RealizeOS',
      description:
        'זה סרגל הניווט. הוא מחולק לחמש קבוצות: Core, Build, Monitor, FABRIC ו-Configure. נעבור יחד על הצעדים הראשונים בעבודה עם המערכת.',
    },
    overview: {
      title: 'סקירה כללית',
      description: 'מתחילים כאן. דף הסקירה מציג במקום אחד את כל המיזמים, הסוכנים והפעילות האחרונה.',
    },
    chat: {
      title: 'שיחה עם ה-AI',
      description:
        'מדברים עם הסוכנים בשפה טבעית: נותנים הוראות, שואלים שאלות או מעבירים משימות. זה הממשק העיקרי שלך.',
    },
    ventures: {
      title: 'ניהול מיזמים',
      description:
        'מיזמים הם יחידות העסק או הפרויקטים שלך. לכל מיזם יש סוכנים, מיומנויות ובסיס ידע משלו. כאן יוצרים את המיזם הראשון.',
    },
    skills: {
      title: 'התקנת מיומנויות',
      description:
        'מיומנויות הן יכולות מוכנות לסוכנים, כמו ניסוח מיילים, מחקר או תזמון. אפשר לעיין בספרייה ולהתקין את מה שצריך.',
    },
    pipelines: {
      title: 'בניית צינורות עבודה',
      description:
        'משרשרים כמה סוכנים וכלים לתהליך אוטומטי אחד. צינורות עבודה מאפשרים לבנות תהליכים מרובי שלבים באופן חזותי.',
    },
    workflows: {
      title: 'יצירת תהליכי עבודה',
      description:
        'מגדירים ב-YAML תבניות של תהליכים שהסוכנים יכולים להריץ. מתאים במיוחד לתהליכים עסקיים שחוזרים על עצמם.',
    },
    activity: {
      title: 'מעקב אחר פעילות',
      description: 'רואים בזמן אמת כל מה שהסוכנים עושים: פעולות, תוצרים ומצב, בכל המיזמים.',
    },
    approvals: {
      title: 'בדיקת אישורים',
      description:
        'כשסוכן צריך אישור של אדם לפעולה רגישה (שליחת מייל, קריאה לשירות חיצוני), הבקשה מופיעה כאן. ההחלטה נשארת בידיים שלך.',
    },
    evolution: {
      title: 'מעקב אחר התפתחות',
      description: 'רואים איך הסוכנים משתפרים עם הזמן: מדדי ביצוע, דפוסי למידה והצעות לשיפור.',
    },
    routing: {
      title: 'הגדרת ניתוב',
      description: 'קובעים איזה מודל AI מטפל באיזו משימה, עם כללי ניתוב לפי עלות, איכות או מהירות.',
    },
    tools: {
      title: 'ניהול כלים',
      description:
        'כלים הם יכולות שהסוכנים משתמשים בהן: חיפוש ברשת, דפדפן, ניהול קבצים ועוד. כאן מפעילים או מכבים אותם.',
    },
    integrations: {
      title: 'חיבור שילובים',
      description:
        'מחברים שירותים חיצוניים כמו Google Workspace, Slack ו-Stripe, כדי שהסוכנים יוכלו לעבוד עם הכלים העסקיים שלך.',
    },
    setup: {
      title: 'הגדרת חיבורים',
      description:
        'מגדירים את מפתחות ה-API של ספקי ה-AI (OpenAI, Anthropic, Google) והגדרות חיבור נוספות. זה הצעד הראשון והחיוני.',
    },
    settings: {
      title: 'הגדרות מערכת',
      description:
        'מכווננים יכולות של המערכת, כמו שערי אישור, דופק תקופתי, זיכרון אוטומטי ומצב יוזם. אפשר גם לנהל מסדי נתונים וספקים.',
    },
    theme: {
      title: 'שפה וערכת נושא',
      description:
        'מחליפים בין ערכת נושא כהה, בהירה או לפי המערכת, ובין עברית לאנגלית. ההעדפה נשמרת אוטומטית. בהצלחה עם RealizeOS!',
    },
  },
}

/** The tour's words for a language ("he", "he-IL", ...); English otherwise. */
export function tourText(language: string | null | undefined): TourText {
  return baseLanguage(language) === 'he' ? HE : EN
}
