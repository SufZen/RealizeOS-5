/**
 * Words on the agent tokens page, in English and Hebrew. The language comes
 * from the locale mechanism (`useLocale().language`); anything that isn't
 * Hebrew reads English. Token names, emails, venture keys and the token
 * itself are data: they are rendered isolated, left to right.
 */
import type { AgentTokenStatus, FormProblem } from '@/lib/agent-tokens'
import { baseLanguage, type Direction } from '@/lib/locale'

export interface AgentTokensText {
  lang: string
  dir: Direction
  settings: string
  title: string
  description: string
  guide: string
  refresh: string
  loading: string
  loadFailed: string
  disabled: string
  notAllowed: string
  createTitle: string
  nameLabel: string
  nameHelp: string
  userLabel: string
  userHelp: string
  venturesLabel: string
  venturesHelp: string
  noVentures: string
  expiryLabel: string
  expiryHelp: string
  create: string
  problems: Record<FormProblem, string>
  createFailed: (detail: string) => string
  createdTitle: string
  createdNote: string
  tokenLabel: (name: string) => string
  copy: string
  copied: string
  copyFailed: string
  /** Before the header line, which is rendered as code. */
  usage: string
  /** After the header line. */
  usageAfter: string
  done: string
  listTitle: string
  empty: string
  emptyBody: string
  status: Record<AgentTokenStatus, string>
  actsFor: string
  created: string
  expires: string
  noExpiry: string
  lastUsed: string
  notUsed: string
  revokedOn: string
  revoke: string
  revokeTitle: (name: string) => string
  revokeBody: string
  revokeConfirm: string
  cancel: string
  revoked: (name: string, withdrawn: number) => string
  revokeFailed: (detail: string) => string
}

const EN: AgentTokensText = {
  lang: 'en',
  dir: 'ltr',
  settings: 'Settings',
  title: 'Agent tokens',
  description:
    'Give each outside agent (Claude, ChatGPT, Cursor, n8n…) its own token, limited to one client’s ventures. Its writes wait for a person to approve them, and you can revoke it at any time.',
  guide: 'How to connect an agent',
  refresh: 'Refresh',
  loading: 'Loading agent tokens',
  loadFailed: 'Couldn’t load agent tokens.',
  disabled:
    'Agent tokens are turned off (features.agent_tokens). No token works and none can be created until an owner turns them on.',
  notAllowed:
    'Only an owner or admin with access to every venture can manage agent tokens. Ask one of them to create a token for your agent.',
  createTitle: 'New agent token',
  nameLabel: 'Name',
  nameHelp: 'A label for people, for example claude-desktop-acme.',
  userLabel: 'Acts for',
  userHelp:
    'The person in users.yaml the agent works for. Their role applies, and the agent never sees more than their ventures.',
  venturesLabel: 'Ventures',
  venturesHelp: 'The client brains the agent may see. Each must be one of that person’s ventures.',
  noVentures: 'There are no ventures yet. Create one first.',
  expiryLabel: 'Expires after (days)',
  expiryHelp: 'Optional, 1 to 3650. Leave it empty for no expiry.',
  create: 'Create token',
  problems: {
    name: 'Use 1 to 64 letters, digits, spaces, dots, dashes or underscores, starting with a letter or digit.',
    user: 'Enter the email of a person in users.yaml.',
    ventures: 'Choose at least one venture.',
    expiry: 'Enter a whole number of days from 1 to 3650, or leave it empty.',
  },
  createFailed: (detail) => `Couldn’t create the token: ${detail}`,
  createdTitle: 'Copy the token now',
  createdNote:
    'You won’t see it again: RealizeOS keeps only a hash. If it gets lost, revoke this token and create a new one.',
  tokenLabel: (name) => `Token for ${name}`,
  copy: 'Copy',
  copied: 'Copied',
  copyFailed: 'Couldn’t copy. Select the token and copy it by hand.',
  usage: 'The agent sends it as',
  usageAfter: 'never in a URL.',
  done: 'I’ve copied it',
  listTitle: 'Tokens',
  empty: 'No agent tokens yet',
  emptyBody:
    'Create one per outside agent, so you can see what each one asked for and revoke it on its own.',
  status: { active: 'Active', expired: 'Expired', revoked: 'Revoked' },
  actsFor: 'Acts for',
  created: 'Created',
  expires: 'Expires',
  noExpiry: 'No expiry',
  lastUsed: 'Last used',
  notUsed: 'Not used yet',
  revokedOn: 'Revoked',
  revoke: 'Revoke',
  revokeTitle: (name) => `Revoke ${name}?`,
  revokeBody:
    'The agent stops working at once, and its writes still waiting for approval are withdrawn. This can’t be undone.',
  revokeConfirm: 'Revoke token',
  cancel: 'Cancel',
  revoked: (name, withdrawn) =>
    withdrawn > 0
      ? `Revoked ${name}. ${withdrawn} waiting ${withdrawn === 1 ? 'write was' : 'writes were'} withdrawn.`
      : `Revoked ${name}.`,
  revokeFailed: (detail) => `Couldn’t revoke the token: ${detail}`,
}

const HE: AgentTokensText = {
  lang: 'he',
  dir: 'rtl',
  settings: 'הגדרות',
  title: 'טוקנים לסוכנים',
  description:
    'כל סוכן חיצוני, כמו Claude, ChatGPT, Cursor או n8n, מקבל טוקן משלו, מוגבל למיזמים של לקוח אחד. הפעולות שלו ממתינות לאישור של אדם, ואפשר לשלול אותו בכל רגע.',
  guide: 'איך מחברים סוכן',
  refresh: 'רענון',
  loading: 'טוען טוקנים',
  loadFailed: 'לא ניתן היה לטעון את הטוקנים.',
  disabled:
    'הטוקנים לסוכנים כבויים (features.agent_tokens). אף טוקן לא עובד ואי אפשר ליצור חדש עד שבעלים יפעילו אותם.',
  notAllowed:
    'רק בעלים או מנהל עם גישה לכל המיזמים יכולים לנהל טוקנים לסוכנים. בקשו מאחד מהם ליצור טוקן לסוכן שלכם.',
  createTitle: 'טוקן חדש לסוכן',
  nameLabel: 'שם',
  nameHelp: 'תווית לבני אדם, למשל claude-desktop-acme.',
  userLabel: 'פועל בשם',
  userHelp:
    'האדם מ-users.yaml שהסוכן עובד עבורו. התפקיד שלו חל על הסוכן, והסוכן לא רואה יותר מהמיזמים שלו.',
  venturesLabel: 'מיזמים',
  venturesHelp: 'המוחות של הלקוחות שהסוכן רשאי לראות. כל אחד מהם חייב להיות מיזם של אותו אדם.',
  noVentures: 'עדיין אין מיזמים. צרו מיזם קודם.',
  expiryLabel: 'תוקף (ימים)',
  expiryHelp: 'לא חובה, בין 1 ל-3650. השאירו ריק לטוקן בלי תפוגה.',
  create: 'יצירת טוקן',
  problems: {
    name: 'עד 64 אותיות באנגלית, ספרות, רווחים, נקודות, מקפים או קווים תחתונים, שמתחילים באות או בספרה.',
    user: 'הזינו את כתובת המייל של אדם מ-users.yaml.',
    ventures: 'בחרו לפחות מיזם אחד.',
    expiry: 'הזינו מספר שלם של ימים בין 1 ל-3650, או השאירו ריק.',
  },
  createFailed: (detail) => `לא ניתן היה ליצור את הטוקן: ${detail}`,
  createdTitle: 'העתיקו את הטוקן עכשיו',
  createdNote:
    'לא תוכלו לראות אותו שוב: RealizeOS שומר רק גיבוב (hash) שלו. אם הוא אבד, שללו את הטוקן וצרו חדש.',
  tokenLabel: (name) => `הטוקן של ${name}`,
  copy: 'העתקה',
  copied: 'הועתק',
  copyFailed: 'ההעתקה נכשלה. סמנו את הטוקן והעתיקו אותו ידנית.',
  usage: 'הסוכן שולח אותו בכותרת',
  usageAfter: 'ואף פעם לא בכתובת URL.',
  done: 'העתקתי',
  listTitle: 'טוקנים',
  empty: 'עדיין אין טוקנים לסוכנים',
  emptyBody: 'צרו טוקן לכל סוכן חיצוני, כדי לראות מה כל אחד ביקש ולשלול אותו בנפרד.',
  status: { active: 'פעיל', expired: 'פג תוקף', revoked: 'נשלל' },
  actsFor: 'פועל בשם',
  created: 'נוצר',
  expires: 'תפוגה',
  noExpiry: 'בלי תפוגה',
  lastUsed: 'שימוש אחרון',
  notUsed: 'עדיין לא בשימוש',
  revokedOn: 'נשלל',
  revoke: 'שלילה',
  revokeTitle: (name) => `לשלול את ${name}?`,
  revokeBody:
    'הסוכן יפסיק לעבוד מיד, והפעולות שלו שעדיין ממתינות לאישור יוסרו מהתור. אי אפשר לחזור מזה.',
  revokeConfirm: 'שלילת הטוקן',
  cancel: 'ביטול',
  revoked: (name, withdrawn) =>
    withdrawn > 0
      ? `הטוקן ${name} נשלל. ${withdrawn === 1 ? 'פעולה ממתינה אחת הוסרה' : `${withdrawn} פעולות ממתינות הוסרו`} מהתור.`
      : `הטוקן ${name} נשלל.`,
  revokeFailed: (detail) => `לא ניתן היה לשלול את הטוקן: ${detail}`,
}

/** The agent tokens words for a language ("he", "he-IL", ...); English otherwise. */
export function agentTokensText(language: string | null | undefined): AgentTokensText {
  return baseLanguage(language) === 'he' ? HE : EN
}
