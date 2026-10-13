/**
 * Words on the approvals surface, in English and Hebrew. The language comes
 * from the locale mechanism (`useLocale().language`: the venture's locale or
 * the person's choice); anything that isn't Hebrew reads English.
 *
 * Text the server provides (an error, a tool's output, who decided) is set
 * apart with `<bdi>` (`isolate`), so a left-to-right error inside a Hebrew
 * sentence, or the other way round, never reorders the sentence around it.
 */
import { createElement, Fragment, type ReactNode } from 'react'
import type { ApprovalStatus, DecisionProblem, Outcome, OutcomeKind } from '@/lib/approval-outcome'
import { baseLanguage } from '@/lib/locale'

/** Server-provided text, isolated from the direction of the sentence around it. */
export function isolate(value: string): ReactNode {
  return createElement('bdi', null, value)
}

/** One sentence from words and isolated values. */
function phrase(...parts: ReactNode[]): ReactNode {
  return createElement(Fragment, null, ...parts)
}

export interface ApprovalText {
  title: string
  description: string
  refresh: string
  tabsLabel: string
  tabHeld: string
  tabDecided: string
  tabExpired: string
  loading: string
  emptyHeld: string
  emptyDecided: string
  emptyExpired: string
  emptyBody: string
  emptyExpiredBody: string
  noteLabel: string
  notePlaceholder: string
  notePlaceholderAnswer: string
  notePlaceholderCredential: string
  dismiss: string
  agent: string
  venture: string
  requestedFor: string
  /** Badge label before an outside agent's token name; the name is rendered isolated (`<bdi>`). */
  outsideAgent: string
  /** Tooltip on that badge: who asked, as the approval queue records it. */
  outsideAgentTitle: (requestedBy: string) => string
  /** On a held item from an outside agent: where the approval boundary is. */
  outsideAgentNote: string
  /** Label before who decided; the name is rendered isolated (`<bdi>`). */
  decidedBy: string
  expires: (relative: string) => string
  expiresAt: (when: string) => string
  /** Label before the expiry time; the time itself is rendered isolated (`<bdi>`). */
  expiredAt: string
  relative: {
    now: string
    minutes: (n: number) => string
    hours: (n: number) => string
    days: (n: number) => string
  }
  status: Record<ApprovalStatus, string>
  actionTypes: Record<string, string>
  reject: string
  no: string
  approve: string
  approveAndRun: string
  yesSendNote: string
  expiredNotice: string
  viewOnly: (role: string) => string
  /** Why someone who may decide other items can't decide a pack verification. */
  ownerOnly: string
  outcome: Record<OutcomeKind, string>
  succeededWith: (output: string) => ReactNode
  failedWith: (error: string) => ReactNode
  notRetried: string
  decisionLogged: string
  /** The decision-log write failed and a retry is queued. */
  decisionQueued: string
  decisionNotLogged: (error?: string | null) => ReactNode
  problem: (p: DecisionProblem) => ReactNode
}

const EN_STATUS: Record<ApprovalStatus, string> = {
  pending: 'Held',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
  answered: 'Answered',
}

const HE_STATUS: Record<ApprovalStatus, string> = {
  pending: 'ממתין',
  approved: 'אושר',
  rejected: 'נדחה',
  expired: 'פג תוקף',
  answered: 'נענה',
}

const EN: ApprovalText = {
  title: 'Approvals',
  description:
    'Payments, messages and questions your agents prepared. Nothing runs until someone here decides.',
  refresh: 'Refresh',
  tabsLabel: 'Approvals',
  tabHeld: 'Held for you',
  tabDecided: 'Decided',
  tabExpired: 'Expired',
  loading: 'Loading approvals',
  emptyHeld: 'Nothing is waiting for you',
  emptyDecided: 'No decisions yet',
  emptyExpired: 'Nothing has expired',
  emptyBody:
    'Approvals appear here when agents attempt gated actions: payments, messages to clients, anything that touches money, contracts or people.',
  emptyExpiredBody:
    'A request no one decided in time lands here. Nothing was done for it, and it can no longer be approved.',
  noteLabel: 'Note for this decision',
  notePlaceholder: 'Optional note...',
  notePlaceholderAnswer: 'Your answer (optional)...',
  notePlaceholderCredential: 'Add the credential in Setup, not here (not stored)',
  dismiss: 'Dismiss',
  agent: 'Agent',
  venture: 'Venture',
  requestedFor: 'For',
  outsideAgent: 'Outside agent:',
  outsideAgentTitle: (requestedBy) => `Requested by ${requestedBy} over MCP`,
  outsideAgentNote:
    'An outside agent asked for this over MCP. Nothing has run: if you approve, it runs once, as that agent and only in its ventures.',
  decidedBy: 'Decided by',
  expires: (relative) => `Expires ${relative}`,
  expiresAt: (when) => `Expires: ${when}`,
  expiredAt: 'Expired:',
  relative: {
    now: 'now',
    minutes: (n) => `in ${n} min`,
    hours: (n) => `in ${n} h`,
    days: (n) => `in ${n} days`,
  },
  status: EN_STATUS,
  actionTypes: {
    send_email: 'Send email',
    publish_content: 'Publish content',
    external_api: 'External API call',
    create_event: 'Create event',
    high_cost_llm: 'High-cost model call',
    skill_input: 'Question from a skill',
    agent_decision: 'Decision requested by an agent',
    agent_input: 'Question from an agent',
    agent_credential: 'Credential requested by an agent',
    pack_verify: 'Pack verification',
    'mcp:run_workflow': 'Run a workflow',
    'mcp:trigger_skill': 'Run a skill',
  },
  reject: 'Reject',
  no: 'No',
  approve: 'Approve',
  approveAndRun: 'Approve & run',
  yesSendNote: 'Yes / send note',
  expiredNotice:
    'This request expired before anyone decided it. Nothing was done, and it can no longer be approved or rejected.',
  viewOnly: (role) =>
    `View only: your role (${role}) can see approvals but can’t approve or reject them.`,
  ownerOnly:
    'A pack’s verification is shared by every venture: only an owner with access to every venture can approve or reject it.',
  outcome: {
    held: 'Waiting for a decision. Nothing has run.',
    expired: 'No one decided in time, so nothing was done.',
    rejected: 'Rejected. Nothing was done.',
    answered: 'Answered.',
    recorded: 'Approved. The decision is recorded; there was nothing to run.',
    succeeded: 'Approved and done.',
    failed: 'Approved, but it failed.',
    unknown:
      'Approved and started, but no result is recorded. If the server restarted while it ran, the outcome is unknown: it is never re-run automatically, so a person has to check.',
    not_started: 'Approved, but it has not run, and it will not start on its own later.',
  },
  succeededWith: (output) => phrase('Approved and done: ', isolate(output)),
  failedWith: (error) => phrase('Approved, but it failed: ', isolate(error)),
  notRetried: 'It is not retried automatically.',
  decisionLogged: 'Added to the decision log.',
  decisionQueued: 'Queued for the decision log; it will be added shortly.',
  decisionNotLogged: (error) =>
    error
      ? phrase('Not added to the decision log: ', isolate(error))
      : 'Not added to the decision log.',
  problem: (p) => {
    switch (p.kind) {
      case 'expired':
        return 'This request expired before anyone decided it, so nothing was done. The list was refreshed.'
      case 'already_decided': {
        const status = p.approval?.status ? EN_STATUS[p.approval.status].toLowerCase() : 'decided'
        const by = p.approval?.decided_by
        return phrase(
          `Someone else already decided this (${status}`,
          by ? phrase(' by ', isolate(by)) : null,
          '). Your decision was not applied. The list was refreshed.',
        )
      }
      case 'gone':
        return 'This request is no longer available. The list was refreshed.'
      case 'forbidden':
        return p.detail
          ? phrase('You can’t decide this request: ', isolate(p.detail))
          : 'You can’t decide this request.'
      case 'session':
        return 'Your session ended, so nothing was decided. Sign in again to continue.'
      case 'network':
        return 'The server could not be reached, so the decision may not have been recorded. The list was refreshed: check this request before trying again.'
      default:
        return phrase(
          'The server could not record this decision',
          p.detail ? phrase(' (', isolate(p.detail), ')') : null,
          '. The list was refreshed: check this request before trying again.',
        )
    }
  },
}

const HE: ApprovalText = {
  title: 'אישורים',
  description: 'תשלומים, הודעות ושאלות שהסוכנים שלך הכינו. שום דבר לא רץ עד שמישהו כאן מחליט.',
  refresh: 'רענון',
  tabsLabel: 'אישורים',
  tabHeld: 'ממתין לך',
  tabDecided: 'הוחלט',
  tabExpired: 'פג תוקף',
  loading: 'טוען אישורים',
  emptyHeld: 'שום דבר לא ממתין לך',
  emptyDecided: 'עדיין אין החלטות',
  emptyExpired: 'אין בקשות שתוקפן פג',
  emptyBody:
    'בקשות מופיעות כאן כשסוכן מנסה לבצע פעולה מוגנת: תשלומים, הודעות ללקוחות, כל מה שנוגע בכסף, בחוזים או באנשים.',
  emptyExpiredBody:
    'בקשה שאף אחד לא החליט עליה בזמן מגיעה לכאן. שום דבר לא בוצע עבורה, ואי אפשר עוד לאשר אותה.',
  noteLabel: 'הערה להחלטה',
  notePlaceholder: 'הערה (לא חובה)...',
  notePlaceholderAnswer: 'התשובה שלך (לא חובה)...',
  notePlaceholderCredential: 'את פרטי הגישה מוסיפים בהגדרות, לא כאן (לא נשמר)',
  dismiss: 'סגירה',
  agent: 'סוכן',
  venture: 'מיזם',
  requestedFor: 'עבור',
  outsideAgent: 'סוכן חיצוני:',
  outsideAgentTitle: (requestedBy) => `התבקש ע״י ${requestedBy} דרך MCP`,
  outsideAgentNote:
    'סוכן חיצוני ביקש את זה דרך MCP. שום דבר לא רץ: אם תאשרו, הפעולה תרוץ פעם אחת, בשם הסוכן ורק במיזמים שלו.',
  decidedBy: 'הוחלט ע״י',
  expires: (relative) => `יפוג ${relative}`,
  expiresAt: (when) => `תוקף עד: ${when}`,
  expiredAt: 'פג תוקף:',
  relative: {
    now: 'עכשיו',
    minutes: (n) => `בעוד ${n} דק׳`,
    hours: (n) => `בעוד ${n} שע׳`,
    days: (n) => `בעוד ${n} ימים`,
  },
  status: HE_STATUS,
  actionTypes: {
    send_email: 'שליחת מייל',
    publish_content: 'פרסום תוכן',
    external_api: 'קריאה לשירות חיצוני',
    create_event: 'יצירת אירוע',
    high_cost_llm: 'קריאה יקרה למודל',
    skill_input: 'שאלה ממיומנות',
    agent_decision: 'החלטה שסוכן ביקש',
    agent_input: 'שאלה מסוכן',
    agent_credential: 'פרטי גישה שסוכן ביקש',
    pack_verify: 'אימות חבילה',
    'mcp:run_workflow': 'הרצת תהליך עבודה',
    'mcp:trigger_skill': 'הפעלת מיומנות',
  },
  reject: 'דחייה',
  no: 'לא',
  approve: 'אישור',
  approveAndRun: 'אישור והרצה',
  yesSendNote: 'כן / שליחת הערה',
  expiredNotice:
    'תוקף הבקשה פג לפני שמישהו החליט עליה. שום דבר לא בוצע, ואי אפשר עוד לאשר או לדחות אותה.',
  viewOnly: (role) => `צפייה בלבד: התפקיד שלך (${role}) מאפשר לראות אישורים, אבל לא לאשר או לדחות.`,
  ownerOnly:
    'אימות של חבילה משותף לכל המיזמים: רק בעלים עם גישה לכל המיזמים יכולים לאשר או לדחות אותו.',
  outcome: {
    held: 'ממתין להחלטה. שום דבר לא רץ.',
    expired: 'אף אחד לא החליט בזמן, ולכן שום דבר לא בוצע.',
    rejected: 'נדחה. שום דבר לא בוצע.',
    answered: 'נענה.',
    recorded: 'אושר. ההחלטה נרשמה; לא היה מה להריץ.',
    succeeded: 'אושר ובוצע.',
    failed: 'אושר, אבל הביצוע נכשל.',
    unknown:
      'אושר והתחיל לרוץ, אבל לא נרשמה תוצאה. אם השרת הופעל מחדש בזמן הריצה, התוצאה לא ידועה: הפעולה לא תורץ שוב אוטומטית, ולכן מישהו צריך לבדוק.',
    not_started: 'אושר, אבל לא רץ, והוא לא יתחיל מעצמו בהמשך.',
  },
  succeededWith: (output) => phrase('אושר ובוצע: ', isolate(output)),
  failedWith: (error) => phrase('אושר, אבל הביצוע נכשל: ', isolate(error)),
  notRetried: 'הוא לא ינוסה שוב אוטומטית.',
  decisionLogged: 'נוסף ליומן ההחלטות.',
  decisionQueued: 'ממתין בתור ליומן ההחלטות; יתווסף בקרוב.',
  decisionNotLogged: (error) =>
    error ? phrase('לא נוסף ליומן ההחלטות: ', isolate(error)) : 'לא נוסף ליומן ההחלטות.',
  problem: (p) => {
    switch (p.kind) {
      case 'expired':
        return 'תוקף הבקשה פג לפני שמישהו החליט עליה, ולכן שום דבר לא בוצע. הרשימה רועננה.'
      case 'already_decided': {
        const status = p.approval?.status ? HE_STATUS[p.approval.status] : 'הוחלט'
        const by = p.approval?.decided_by
        return phrase(
          `מישהו אחר כבר החליט על הבקשה (${status}`,
          by ? phrase(' ע״י ', isolate(by)) : null,
          '). ההחלטה שלך לא נרשמה. הרשימה רועננה.',
        )
      }
      case 'gone':
        return 'הבקשה כבר לא זמינה. הרשימה רועננה.'
      case 'forbidden':
        return p.detail
          ? phrase('אין לך הרשאה להחליט על הבקשה: ', isolate(p.detail))
          : 'אין לך הרשאה להחליט על הבקשה.'
      case 'session':
        return 'החיבור שלך הסתיים, ולכן שום החלטה לא נרשמה. יש להתחבר שוב כדי להמשיך.'
      case 'network':
        return 'לא ניתן היה להגיע לשרת, וייתכן שההחלטה לא נרשמה. הרשימה רועננה: כדאי לבדוק את הבקשה לפני שמנסים שוב.'
      default:
        return phrase(
          'השרת לא הצליח לרשום את ההחלטה',
          p.detail ? phrase(' (', isolate(p.detail), ')') : null,
          '. הרשימה רועננה: כדאי לבדוק את הבקשה לפני שמנסים שוב.',
        )
    }
  },
}

/** The approvals words for a language ("he", "he-IL", ...); English otherwise. */
export function approvalText(language: string | null | undefined): ApprovalText {
  return baseLanguage(language) === 'he' ? HE : EN
}

/** The sentence for an outcome, with the tool's output or error (isolated) when there is one. */
export function outcomeMessage(outcome: Outcome, text: ApprovalText): ReactNode {
  if (outcome.kind === 'succeeded' && outcome.detail) return text.succeededWith(outcome.detail)
  if (outcome.kind === 'failed') {
    const detail = outcome.detail?.trim()
    const head = detail ? text.failedWith(detail) : text.outcome.failed
    const ended = /[.!?]$/.test(detail || text.outcome.failed)
    return phrase(head, ended ? ' ' : '. ', text.notRetried)
  }
  return text.outcome[outcome.kind]
}

/** "in 5 min", "in 2 h", "in 3 days" or "now"; the absolute time stays in the tooltip. */
export function relativeExpiry(iso: string, now: number, text: ApprovalText): string {
  const ms = new Date(iso).getTime() - now
  if (Number.isNaN(ms)) return ''
  if (ms <= 0) return text.relative.now
  const h = ms / 3_600_000
  if (h < 1) return text.relative.minutes(Math.max(1, Math.round(ms / 60_000)))
  if (h < 48) return text.relative.hours(Math.round(h))
  return text.relative.days(Math.round(h / 24))
}
