import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import {
  Building2,
  Check,
  CircleDot,
  FileText,
  Inbox,
  LayoutGrid,
  List,
  Moon,
  MoreHorizontal,
  Search,
  ShieldCheck,
  Sun,
  Trash2,
  Upload,
  Activity,
  BookOpen,
  MessageCircle,
  Settings,
  Plus,
  RotateCcw,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useTheme } from '@/components/theme-provider'
import { useToast } from '@/components/ui/toast'
import { Button, IconButton } from '@/components/ui/button'
import { Badge, Kbd, StatusDot } from '@/components/ui/badge'
import { Panel } from '@/components/ui/panel'
import { TitleBlock } from '@/components/ui/title-block'
import { Tabs, Segmented } from '@/components/ui/tabs'
import { Switch } from '@/components/ui/switch'
import { Field } from '@/components/ui/field'
import { Dialog } from '@/components/ui/dialog'
import { Stamp, type Decision } from '@/components/ui/stamp'
import { Trail, SourceRef, type TrailStep } from '@/components/ui/trail'
import { Stat } from '@/components/ui/stat'
import { EmptyState } from '@/components/ui/empty-state'
import { CommandPalette, type Command } from '@/components/ui/command-palette'
import { Skeleton } from '@/components/ui/skeleton'

/* ------------------------------------------------------------------ */
/* Copy — bilingual, because Hebrew is first-class                     */
/* ------------------------------------------------------------------ */

type Lang = 'en' | 'he'

const T = {
  en: {
    venture: 'Ramat Aviv Towers',
    reqTitle: 'Payment request 14 · Ashtrom Contractors',
    reqBody:
      'Frame complete, floor 6. The amount matches milestone M6 in the signed schedule; the site photo and the engineer’s sign-off are attached.',
    amount: 'Amount',
    milestone: 'Milestone',
    approve: 'Approve payment',
    reject: 'Return to contractor',
    approvedMonth: 'Approved this month',
    held: 'Waiting for you',
    trail: [
      'Read payment request PR-14 from the shared drive',
      'Matched it to milestone M6 in the contract schedule',
      'Checked the engineer’s sign-off for floor 6',
    ],
    approvedBy: 'Approved by Dana Levi',
  },
  he: {
    venture: 'מגדלי רמת אביב',
    reqTitle: 'חשבון 14 · אשטרום קבלנות',
    reqBody:
      'שלד קומה 6 הושלם. הסכום תואם את אבן הדרך M6 בלוח החתום; תמונת אתר ואישור המהנדס מצורפים.',
    amount: 'סכום',
    milestone: 'אבן דרך',
    approve: 'אישור תשלום',
    reject: 'החזרה לקבלן',
    approvedMonth: 'אושר החודש',
    held: 'ממתין לך',
    trail: [
      'קראתי את חשבון 14 מהתיקייה המשותפת',
      'התאמתי אותו לאבן דרך M6 בלוח החוזה',
      'בדקתי את אישור המהנדס לקומה 6',
    ],
    approvedBy: 'אושר ע״י דנה לוי',
  },
}

/* ------------------------------------------------------------------ */
/* Small layout helpers for this page only                             */
/* ------------------------------------------------------------------ */

function Section({
  id,
  title,
  lede,
  children,
}: {
  id: string
  title: string
  lede?: string
  children: ReactNode
}) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-h`}
      className="scroll-mt-20 py-12 border-t border-border"
    >
      <div className="mb-6 max-w-[68ch]">
        <h2 id={`${id}-h`} className="text-[1.375rem] font-semibold tracking-tight m-0">
          {title}
        </h2>
        {lede && <p className="mt-2 text-muted-foreground leading-relaxed">{lede}</p>}
      </div>
      {children}
    </section>
  )
}

function Spec({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="grid gap-3">
      <div className="text-xs text-subtle-foreground">{name}</div>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Hero — the signature moment, live                                   */
/* ------------------------------------------------------------------ */

const ILS_BY_LANG: Record<Lang, Intl.NumberFormat> = {
  en: new Intl.NumberFormat('en-IL', {
    style: 'currency',
    currency: 'ILS',
    maximumFractionDigits: 0,
  }),
  he: new Intl.NumberFormat('he-IL', {
    style: 'currency',
    currency: 'ILS',
    maximumFractionDigits: 0,
  }),
}
const ILS = ILS_BY_LANG.en

function ApprovalHero({ lang }: { lang: Lang }) {
  const t = T[lang]
  const money = ILS_BY_LANG[lang]
  const [decision, setDecision] = useState<Decision>('held')
  const [busy, setBusy] = useState(false)
  const [total, setTotal] = useState(1_284_500)

  const steps: TrailStep[] = useMemo(() => {
    const base: TrailStep[] = t.trail.map((title, i) => ({
      id: `s${i}`,
      state: 'done',
      title: (
        <>
          {title}
          <SourceRef
            n={i + 1}
            title={['PR-14.pdf', 'Contract schedule, rev C', 'Engineer sign-off F6.pdf'][i] ?? ''}
          />
        </>
      ),
      meta: ['Drive · 09:12', 'FABRIC · contracts', 'Drive · 09:13'][i],
    }))
    if (decision === 'held') {
      base.push({ id: 'held', state: 'held', title: t.held, meta: lang === 'he' ? 'עכשיו' : 'now' })
    } else {
      base.push({
        id: 'done',
        state: decision === 'approved' ? 'done' : 'failed',
        title:
          decision === 'approved'
            ? t.approvedBy
            : lang === 'he'
              ? 'הוחזר לקבלן'
              : 'Returned to contractor',
        meta: '14:02',
        fresh: true,
      })
    }
    return base
  }, [decision, t, lang])

  function decide(d: Decision) {
    setBusy(true)
    // A short wait stands in for the server round-trip so the busy state is visible.
    window.setTimeout(() => {
      setBusy(false)
      setDecision(d)
      if (d === 'approved') setTotal((v) => v + 412_800)
    }, 650)
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]" lang={lang}>
      <Panel
        held={decision === 'held'}
        title={t.reqTitle}
        actions={
          decision === 'held' ? (
            <Badge tone="accent" dot>
              {t.held}
            </Badge>
          ) : (
            <IconButton label="Replay" size="sm" onClick={() => setDecision('held')}>
              <RotateCcw />
            </IconButton>
          )
        }
        footer={
          decision === 'held' ? (
            <div className="flex flex-wrap gap-2 justify-end">
              <Button variant="ghost" disabled={busy} onClick={() => decide('rejected')}>
                {t.reject}
              </Button>
              <Button variant="approve" busy={busy} onClick={() => decide('approved')}>
                <Check aria-hidden />
                {t.approve}
              </Button>
            </div>
          ) : undefined
        }
      >
        <div className="relative">
          <div className="grid gap-4">
            <p className="m-0 text-[15px] leading-relaxed text-muted-foreground max-w-[60ch]">
              {t.reqBody}
            </p>
            <dl className="grid grid-cols-2 gap-4 m-0 max-w-sm">
              <div>
                <dt className="text-xs text-subtle-foreground">{t.amount}</dt>
                <dd className="m-0 mt-1 text-lg font-semibold tabular">{money.format(412_800)}</dd>
              </div>
              <div>
                <dt className="text-xs text-subtle-foreground">{t.milestone}</dt>
                <dd className="m-0 mt-1 text-lg font-semibold">M6</dd>
              </div>
            </dl>
            <Trail steps={steps} />
          </div>
          {/* The stamp lands on the sheet, over the content, like ink on paper */}
          {decision !== 'held' && (
            <div className="absolute top-0 end-0 sm:top-2 sm:end-4 pointer-events-none">
              <Stamp decision={decision} by="Dana · 14:02" strike />
            </div>
          )}
        </div>
      </Panel>
      <div className="rz-panel p-4 grid content-start gap-5 self-start">
        <Stat
          label={t.approvedMonth}
          value={total}
          format={(n) => money.format(Math.round(n))}
          delta={12}
          deltaLabel=" vs Sept"
        />
        <div className="rz-divider" />
        <div className="grid gap-2 text-sm">
          <div className="flex items-center gap-2">
            <StatusDot state="agent" live /> <span>Payment check agent</span>
            <span className="ms-auto text-xs text-subtle-foreground">running</span>
          </div>
          <div className="flex items-center gap-2">
            <StatusDot state="active" /> <span>Tender register</span>
            <span className="ms-auto text-xs text-subtle-foreground">idle</span>
          </div>
          <div className="flex items-center gap-2">
            <StatusDot state="review" /> <span>Investor report</span>
            <span className="ms-auto text-xs text-subtle-foreground">2 held</span>
          </div>
        </div>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Colour                                                              */
/* ------------------------------------------------------------------ */

const SWATCHES: { group: string; items: [string, string][] }[] = [
  {
    group: 'Surfaces',
    items: [
      ['--rz-bg', 'Page'],
      ['--rz-bg-sunken', 'Sidebar, wells'],
      ['--rz-bg-raised', 'Panels'],
      ['--rz-surface', 'Inputs, quiet buttons'],
      ['--rz-surface-active', 'Pressed, selected'],
    ],
  },
  {
    group: 'Ink',
    items: [
      ['--rz-fg', 'Text'],
      ['--rz-fg-muted', 'Secondary text'],
      ['--rz-fg-subtle', 'Labels, meta'],
      ['--rz-fg-faint', 'Disabled, placeholder'],
    ],
  },
  {
    group: 'Meaning',
    items: [
      ['--rz-accent', 'Brand · hi-vis yellow'],
      ['--rz-success', 'Approved, done'],
      ['--rz-warning', 'Needs attention'],
      ['--rz-danger', 'Redline: failed, rejected'],
      ['--rz-info', 'Survey pin: links, sources'],
      ['--rz-agent', 'Agent activity'],
    ],
  },
]

function Swatches({ mode }: { mode: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  useEffect(() => {
    // Wait a frame: the theme provider applies data-mode in its own effect,
    // which runs after this child's effect.
    const raf = requestAnimationFrame(() => {
      const cs = getComputedStyle(document.documentElement)
      const v: Record<string, string> = {}
      SWATCHES.forEach((g) =>
        g.items.forEach(([name]) => (v[name] = cs.getPropertyValue(name).trim())),
      )
      setValues(v)
    })
    return () => cancelAnimationFrame(raf)
  }, [mode])
  return (
    <div ref={ref} className="grid gap-8">
      {SWATCHES.map((g) => (
        <div key={g.group}>
          <h3 className="text-sm font-medium text-muted-foreground mb-3">{g.group}</h3>
          <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 lg:grid-cols-6">
            {g.items.map(([name, role]) => (
              <div key={name} className="rz-panel overflow-hidden">
                <div
                  className="h-16 border-b border-border"
                  style={{ background: `var(${name})` }}
                />
                <div className="p-3 grid gap-0.5">
                  <span className="text-sm font-medium">{role}</span>
                  <code className="bg-transparent p-0 text-[11px] text-subtle-foreground">
                    {name}
                  </code>
                  <code className="bg-transparent p-0 text-[11px] text-subtle-foreground">
                    {values[name]}
                  </code>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Motion                                                              */
/* ------------------------------------------------------------------ */

const SETTLE = [
  0, 0.029, 0.101, 0.194, 0.295, 0.396, 0.491, 0.577, 0.653, 0.719, 0.775, 0.822, 0.86, 0.892,
  0.917, 0.937, 0.953, 0.965, 0.974, 0.982, 0.987, 0.991, 0.994, 0.996, 1,
]
const BOUNCE = [
  0, 0.063, 0.209, 0.386, 0.561, 0.713, 0.836, 0.926, 0.987, 1.024, 1.043, 1.049, 1.047, 1.04,
  1.031, 1.023, 1.015, 1.009, 1.004, 1.001, 0.999, 0.998, 0.998, 0.998, 1,
]

function Curve({ points }: { points: number[] }) {
  const d = points.map((v, i) => `${(i / (points.length - 1)) * 160},${70 - v * 56}`).join(' ')
  return (
    <svg viewBox="-4 -4 168 82" className="w-full h-24" aria-hidden>
      <path d="M0 14h160" stroke="var(--rz-border-strong)" strokeDasharray="3 3" fill="none" />
      <path d="M0 70h160" stroke="var(--rz-border)" fill="none" />
      <polyline
        points={d}
        fill="none"
        stroke="var(--rz-accent)"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  )
}

const MOTION_ROWS: [string, string, string][] = [
  ['--rz-dur-instant', '80ms', 'Press feedback'],
  ['--rz-dur-quick', '140ms', 'Hover, menus, exits'],
  ['--rz-dur-base', '220ms', 'Popovers, toasts, route change'],
  ['--rz-dur-slow', '360ms', 'Sheets, list arrival'],
  ['--rz-dur-deliberate', '560ms', 'The stamp. Nothing else.'],
]

function MotionLab() {
  const [run, setRun] = useState(0)
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Panel title="Productive" className="lg:col-span-1">
        <p className="m-0 mb-4 text-sm text-muted-foreground leading-relaxed">
          The default register. Fast, quiet, interruptible. If someone notices it, it is too slow.
        </p>
        <table className="rz-table">
          <tbody>
            {MOTION_ROWS.map(([token, ms, use]) => (
              <tr key={token}>
                <td className="tabular w-16">{ms}</td>
                <td className="text-muted-foreground">{use}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel
        title="Expressive · springs"
        className="lg:col-span-2"
        actions={
          <Button size="sm" onClick={() => setRun((r) => r + 1)}>
            <RotateCcw aria-hidden /> Replay
          </Button>
        }
      >
        <p className="m-0 mb-4 text-sm text-muted-foreground leading-relaxed max-w-[60ch]">
          For moments that change something real. Curves come from spring physics, compiled to CSS{' '}
          <code>linear()</code>, so no animation library ships to the browser.
        </p>
        <div className="grid gap-6 sm:grid-cols-2">
          {(
            [
              [
                'Settle',
                SETTLE,
                'var(--rz-spring-settle)',
                '300ms',
                'Tabs ink, segmented thumb, dialogs',
              ],
              [
                'Bounce',
                BOUNCE,
                'var(--rz-spring-bounce)',
                '480ms',
                'Toasts, switch knob, the stamp',
              ],
            ] as const
          ).map(([name, pts, ease, dur, use]) => (
            <div key={name} className="grid gap-2">
              <div className="flex items-baseline justify-between">
                <span className="font-medium">{name}</span>
                <span className="text-xs text-subtle-foreground tabular">{dur}</span>
              </div>
              <Curve points={[...pts]} />
              <div className="relative h-8 rounded-[5px] bg-[var(--rz-bg-sunken)] border border-border overflow-hidden">
                <span
                  key={run}
                  className="absolute top-1.5 start-1.5 h-5 w-5 rounded-[4px] bg-[var(--rz-accent)]"
                  style={{
                    animation: `ds-travel ${dur} ${ease} 150ms both`,
                  }}
                />
              </div>
              <span className="text-xs text-subtle-foreground">{use}</span>
            </div>
          ))}
        </div>
        <style>{`@keyframes ds-travel{from{inset-inline-start:6px}to{inset-inline-start:calc(100% - 26px)}}`}</style>
      </Panel>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Market comparison                                                   */
/* ------------------------------------------------------------------ */

const MARKET: [string, string, string, string][] = [
  [
    'Linear',
    'Speed, ⌘K everywhere, a restrained palette and quick motion',
    'Keyboard-first command palette; sub-200ms productive motion',
    'Its monochrome anonymity: RealizeOS needs a field identity',
  ],
  [
    'Vercel Geist',
    'Strict grey scales, semantic colour steps, a type family made for UI',
    'Scale discipline: every surface and line step has one job',
    'Developer-only tone',
  ],
  [
    'Stripe Dashboard',
    'Dense financial data that still feels approachable; contrast-tested colour',
    'Figures shown with their context and source',
    'Neutral fintech blue',
  ],
  [
    'IBM Carbon',
    'Productive vs expressive motion; enterprise accessibility',
    'The two motion registers',
    'Visual heaviness',
  ],
  [
    'Material 3 Expressive',
    'Physics-based springs as motion tokens',
    'Springs as tokens, compiled to CSS',
    'Playful shapes and colour blocking',
  ],
  [
    'n8n · Relevance AI · Lindy',
    'Agent builders with run logs and canvases',
    'A step-by-step run trace',
    'Node canvases: people here approve, they don’t wire graphs',
  ],
  [
    'LangSmith',
    'Agent trace trees with tokens and latency',
    'Every step inspectable',
    'Developer telemetry in a people-facing surface',
  ],
  [
    'Procore · Autodesk Build',
    'AEC workflows: submittals, RFIs, approvals, stamps',
    'The field vocabulary: stamps, revisions, sheet references',
    'Enterprise density and dated visuals',
  ],
]

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

const NAV = [
  ['moment', 'The moment'],
  ['principles', 'Principles'],
  ['colour', 'Colour'],
  ['type', 'Type'],
  ['motion', 'Motion'],
  ['controls', 'Controls'],
  ['display', 'Display'],
  ['overlays', 'Overlays'],
  ['field', 'Field language'],
  ['market', 'Market'],
] as const

export default function DesignPage() {
  const { resolved, setTheme } = useTheme()
  const toast = useToast()
  const navigate = useNavigate()
  const [lang, setLang] = useState<Lang>('en')
  const [density, setDensity] = useState<'compact' | 'comfy'>('compact')
  const [tab, setTab] = useState<'held' | 'approved' | 'all'>('held')
  const [view, setView] = useState<'list' | 'board'>('list')
  const [notify, setNotify] = useState(true)
  const [autonomy, setAutonomy] = useState(false)
  const [dialog, setDialog] = useState(false)
  const [palette, setPalette] = useState(false)
  const [scope, setScope] = useState<string[]>(['Ramat Aviv Towers'])
  const [invalid, setInvalid] = useState(false)

  useEffect(() => {
    document.documentElement.setAttribute('data-density', density)
    return () => document.documentElement.setAttribute('data-density', 'compact')
  }, [density])

  const commands: Command[] = useMemo(
    () => [
      {
        id: 'approvals',
        group: 'Go to',
        label: 'Approvals',
        icon: ShieldCheck,
        keywords: 'אישורים held',
        hint: '3 held',
        run: () => navigate('/approvals'),
      },
      {
        id: 'chat',
        group: 'Go to',
        label: 'Chat',
        icon: MessageCircle,
        keywords: 'צ׳אט',
        run: () => navigate('/chat'),
      },
      {
        id: 'activity',
        group: 'Go to',
        label: 'Activity',
        icon: Activity,
        run: () => navigate('/activity'),
      },
      {
        id: 'knowledge',
        group: 'Go to',
        label: 'Knowledge',
        icon: BookOpen,
        keywords: 'fabric brain ידע',
        run: () => navigate('/knowledge'),
      },
      {
        id: 'settings',
        group: 'Go to',
        label: 'Settings',
        icon: Settings,
        run: () => navigate('/settings'),
      },
      {
        id: 'upload',
        group: 'Do',
        label: 'Add documents to the company brain',
        icon: Upload,
        run: () => toast.info('Upload opened'),
      },
      {
        id: 'venture',
        group: 'Do',
        label: 'New venture',
        icon: Plus,
        run: () => toast.info('New venture'),
      },
      {
        id: 'theme',
        group: 'Do',
        label: resolved === 'dark' ? 'Switch to paper (light)' : 'Switch to night (dark)',
        icon: resolved === 'dark' ? Sun : Moon,
        run: () => setTheme(resolved === 'dark' ? 'light' : 'dark'),
      },
    ],
    [navigate, toast, resolved, setTheme],
  )

  return (
    <div dir={lang === 'he' ? 'rtl' : 'ltr'} className="min-h-screen bg-background text-foreground">
      {/* Toolbar */}
      <header className="sticky top-0 z-20 fx-glass border-b border-border">
        <div className="mx-auto max-w-[1240px] px-4 sm:px-6 h-14 flex items-center gap-3">
          <span className="font-brand font-semibold text-[17px] fx-gradient-text">RealizeOS</span>
          <span className="text-sm text-muted-foreground hidden sm:inline">Design system</span>
          <div className="ms-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPalette(true)}
              className="rz-btn rz-btn--sm hidden md:inline-flex text-muted-foreground"
            >
              <Search aria-hidden /> Search <Kbd>Ctrl K</Kbd>
            </button>
            <Segmented
              label="Language"
              value={lang}
              onChange={setLang}
              items={[
                { value: 'en', label: 'EN' },
                { value: 'he', label: 'עב' },
              ]}
            />
            <IconButton
              label={resolved === 'dark' ? 'Paper (light)' : 'Night (dark)'}
              onClick={() => setTheme(resolved === 'dark' ? 'light' : 'dark')}
            >
              {resolved === 'dark' ? <Sun /> : <Moon />}
            </IconButton>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1240px] px-4 sm:px-6 lg:grid lg:grid-cols-[180px_minmax(0,1fr)] lg:gap-10">
        <nav aria-label="Sections" className="hidden lg:block sticky top-14 self-start py-12">
          <ul className="m-0 p-0 list-none grid gap-0.5 text-sm">
            {NAV.map(([id, label]) => (
              <li key={id}>
                <a
                  href={`#${id}`}
                  className="block rounded-[5px] px-2 py-1.5 text-muted-foreground no-underline hover:text-foreground hover:bg-surface-700"
                >
                  {label}
                </a>
              </li>
            ))}
          </ul>
        </nav>

        <main className="min-w-0 pb-24">
          {/* Hero */}
          <section id="moment" className="pt-10 pb-12 relative">
            <div className="rz-drafting-grid absolute inset-x-0 top-0 h-[420px] -z-0 pointer-events-none [mask-image:linear-gradient(to_bottom,black,transparent)]" />
            <div className="relative">
              <h1 className="m-0 text-[2.25rem] sm:text-[2.75rem] leading-[1.05] font-medium tracking-[-0.03em] max-w-[18ch]">
                People decide. The system prepares.
              </h1>
              <p className="mt-4 mb-8 text-[15px] leading-relaxed text-muted-foreground max-w-[62ch]">
                Drawing Set is the design system for RealizeOS. It is built around the moment that
                matters most to a field practice: an agent has prepared something that touches
                money, and a person decides. Try it below.
              </p>
              <ApprovalHero lang={lang} />
            </div>
          </section>

          <Section
            id="principles"
            title="Principles"
            lede="Six rules every screen is checked against."
          >
            <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
              {[
                [
                  'Colour is a word, not a coat of paint',
                  'Yellow means the brand or “held for you”. Green is a decision made. Red is a redline. If a colour carries no meaning, it is grey.',
                ],
                [
                  'Show the source',
                  'A figure without a source is a guess. Every number an agent produces links to the document it came from.',
                ],
                [
                  'Calm by default, one loud moment',
                  'Productive motion is quick and unnoticed. The stamp is the one expressive moment, and it only plays when a decision lands.',
                ],
                [
                  'Two languages, one voice',
                  'Every component is built with logical properties and checked in Hebrew. IBM Plex has a real Hebrew cut, so the type does not change voice between languages.',
                ],
                [
                  'Keyboard first, not keyboard only',
                  'Ctrl K reaches every page and action. Every control has a visible focus state and a name.',
                ],
                [
                  'The field’s vocabulary',
                  'Title blocks, sheet references, leader lines, stamps and redlines. The people using this read drawings all day.',
                ],
              ].map(([h, p]) => (
                <div key={h}>
                  <h3 className="m-0 text-[15px] font-semibold">{h}</h3>
                  <p className="mt-1.5 mb-0 text-sm text-muted-foreground leading-relaxed">{p}</p>
                </div>
              ))}
            </div>
          </Section>

          <Section
            id="colour"
            title="Colour"
            lede="Two modes from one set of names. Night site (dark) for long sessions; paper (light) for the office and for print. Surfaces are blueprint graphite, never pure black."
          >
            <Swatches mode={resolved} />
          </Section>

          <Section
            id="type"
            title="Type"
            lede="IBM Plex Sans and IBM Plex Sans Hebrew, with Plex Mono for code and IDs. Five sizes do almost all of the product’s work."
          >
            <div className="rz-panel divide-y divide-border">
              {(
                [
                  [
                    '22 / Page title',
                    'text-[1.375rem] font-semibold tracking-tight',
                    'Approvals for Ramat Aviv Towers',
                    'אישורים למגדלי רמת אביב',
                  ],
                  ['18 / Panel title', 'text-lg font-semibold', 'Payment request 14', 'חשבון 14'],
                  [
                    '16 / Reading',
                    'text-base',
                    'The amount matches milestone M6 in the signed schedule.',
                    'הסכום תואם את אבן הדרך M6 בלוח החתום.',
                  ],
                  [
                    '14 / Body',
                    'text-[14px]',
                    'Agents prepare; people decide.',
                    'הסוכנים מכינים; האנשים מחליטים.',
                  ],
                  [
                    '13 / Dense UI',
                    'text-[13px]',
                    'Ashtrom Contractors · floor 6',
                    'אשטרום קבלנות · קומה 6',
                  ],
                  [
                    '12 / Caption',
                    'text-xs text-muted-foreground',
                    'Updated 4 minutes ago',
                    'עודכן לפני 4 דקות',
                  ],
                ] as const
              ).map(([name, cls, en, he]) => (
                <div
                  key={name}
                  className="grid gap-2 p-4 sm:grid-cols-[140px_1fr_1fr] sm:items-baseline"
                >
                  <span className="text-xs text-subtle-foreground tabular">{name}</span>
                  <span className={cls}>{en}</span>
                  <span className={cls} dir="rtl" lang="he">
                    {he}
                  </span>
                </div>
              ))}
              <div className="grid gap-2 p-4 sm:grid-cols-[140px_1fr] sm:items-baseline">
                <span className="text-xs text-subtle-foreground">36 / Figure</span>
                <span className="text-[2.25rem] font-medium tracking-[-0.025em] tabular">
                  ₪1,697,300
                </span>
              </div>
            </div>
          </Section>

          <Section
            id="motion"
            title="Motion"
            lede="Two registers, after IBM Carbon: productive for everything, expressive for the few moments that change something real. Reduced-motion settings keep fades and drop all travel."
          >
            <MotionLab />
          </Section>

          <Section id="controls" title="Controls">
            <div className="grid gap-8 lg:grid-cols-2 items-start">
              <Panel title="Buttons">
                <div className="grid gap-5">
                  <Spec name="Variants · one primary per view">
                    <Button variant="primary">Run audit</Button>
                    <Button>Export</Button>
                    <Button variant="ghost">Cancel</Button>
                    <Button variant="approve">
                      <Check aria-hidden /> Approve
                    </Button>
                    <Button variant="danger">
                      <Trash2 aria-hidden /> Delete venture
                    </Button>
                  </Spec>
                  <Spec name="Sizes and states">
                    <Button size="sm">Small</Button>
                    <Button>Default</Button>
                    <Button size="lg" variant="primary">
                      Large
                    </Button>
                    <Button busy>Saving</Button>
                    <Button disabled>Disabled</Button>
                  </Spec>
                  <Spec name="Icon buttons carry a name and a tooltip">
                    <IconButton label="Upload">
                      <Upload />
                    </IconButton>
                    <IconButton label="More actions">
                      <MoreHorizontal />
                    </IconButton>
                    <IconButton label="Search">
                      <Search />
                    </IconButton>
                  </Spec>
                </div>
              </Panel>
              <Panel title="Inputs">
                <form
                  className="grid gap-4"
                  onSubmit={(e) => {
                    e.preventDefault()
                    setInvalid(true)
                  }}
                >
                  <Field label="Venture name" help="Shown to everyone in this venture.">
                    <input className="rz-input" defaultValue="Ramat Aviv Towers" />
                  </Field>
                  <Field
                    label="Approval limit"
                    error={
                      invalid
                        ? 'Enter an amount above ₪0, or leave it empty for no limit.'
                        : undefined
                    }
                  >
                    <input
                      className={invalid ? 'rz-input rz-nudge' : 'rz-input'}
                      defaultValue="-5000"
                      inputMode="numeric"
                    />
                  </Field>
                  <Field label="Market pack">
                    <select className="rz-select" defaultValue="il">
                      <option value="il">Israel · Hebrew</option>
                      <option value="pt">Portugal · Portuguese</option>
                    </select>
                  </Field>
                  <div className="rz-input-wrap">
                    <Search aria-hidden />
                    <input
                      className="rz-input"
                      placeholder="Search documents"
                      aria-label="Search documents"
                    />
                    <Kbd>/</Kbd>
                  </div>
                  <div className="flex gap-2">
                    <Button type="submit" variant="primary">
                      Save limit
                    </Button>
                    <Button variant="ghost" onClick={() => setInvalid(false)}>
                      Reset
                    </Button>
                  </div>
                </form>
              </Panel>
              <Panel title="Choices">
                <div className="grid gap-5">
                  <Switch
                    checked={notify}
                    onChange={setNotify}
                    label="WhatsApp me when something is held"
                    description="Only for approvals over your limit."
                  />
                  <Switch
                    checked={autonomy}
                    onChange={setAutonomy}
                    label="Let agents file documents without asking"
                    description="Never applies to payments or contracts."
                  />
                  <label className="flex items-center gap-2.5 text-sm cursor-pointer">
                    <input type="checkbox" className="rz-check" defaultChecked /> Include site
                    photos in the investor report
                  </label>
                  <Spec name="Filter chips">
                    {['Ramat Aviv Towers', 'Lisbon Riverside', 'Haifa Port Lofts'].map((v) => (
                      <button
                        key={v}
                        type="button"
                        className="rz-chip"
                        aria-pressed={scope.includes(v)}
                        onClick={() =>
                          setScope((s) => (s.includes(v) ? s.filter((x) => x !== v) : [...s, v]))
                        }
                      >
                        <Building2 aria-hidden />
                        {v}
                      </button>
                    ))}
                  </Spec>
                </div>
              </Panel>
              <Panel title="Tabs and segments">
                <div className="grid gap-6">
                  <Tabs
                    label="Approvals"
                    value={tab}
                    onChange={setTab}
                    items={[
                      { value: 'held', label: 'Held', count: 3 },
                      { value: 'approved', label: 'Approved', count: 28 },
                      { value: 'all', label: 'All' },
                    ]}
                  />
                  <Segmented
                    label="View"
                    value={view}
                    onChange={setView}
                    items={[
                      { value: 'list', label: 'List', icon: <List /> },
                      { value: 'board', label: 'Board', icon: <LayoutGrid /> },
                    ]}
                  />
                  <Segmented
                    label="Density"
                    value={density}
                    onChange={setDensity}
                    items={[
                      { value: 'compact', label: 'Compact' },
                      { value: 'comfy', label: 'Comfortable' },
                    ]}
                  />
                </div>
              </Panel>
            </div>
          </Section>

          <Section id="display" title="Display">
            <div className="grid gap-8 lg:grid-cols-2 items-start">
              <Panel title="Status">
                <div className="grid gap-5">
                  <Spec name="Badges say the state in words">
                    <Badge tone="accent" dot>
                      Held
                    </Badge>
                    <Badge tone="success">Approved</Badge>
                    <Badge tone="danger">Rejected</Badge>
                    <Badge tone="warning">Over budget</Badge>
                    <Badge tone="info">3 sources</Badge>
                    <Badge tone="agent">Agent</Badge>
                    <Badge>Draft</Badge>
                  </Spec>
                  <Spec name="Dots · only running work breathes">
                    <span className="inline-flex items-center gap-2 text-sm">
                      <StatusDot state="agent" live /> Running
                    </span>
                    <span className="inline-flex items-center gap-2 text-sm">
                      <StatusDot state="active" /> Healthy
                    </span>
                    <span className="inline-flex items-center gap-2 text-sm">
                      <StatusDot state="review" /> Needs you
                    </span>
                    <span className="inline-flex items-center gap-2 text-sm">
                      <StatusDot state="error" /> Failed
                    </span>
                    <span className="inline-flex items-center gap-2 text-sm">
                      <StatusDot /> Idle
                    </span>
                  </Spec>
                  <Spec name="People are round; agents are sheet tabs">
                    <span className="rz-avatar">DL</span>
                    <span className="rz-avatar">AS</span>
                    <span className="rz-avatar rz-avatar--agent">PC</span>
                    <span className="rz-avatar rz-avatar--agent">TR</span>
                  </Spec>
                </div>
              </Panel>
              <Panel title="Figures">
                <div className="grid grid-cols-2 gap-6">
                  <Stat
                    label="Hours saved this month"
                    value={46}
                    unit="h"
                    delta={18}
                    source={<SourceRef n={1} title="Value report, Sept" />}
                  />
                  <Stat label="Payments held" value={3} delta={-40} goodWhen="down" />
                </div>
              </Panel>
              <Panel title="Table" flush className="lg:col-span-2">
                <div className="overflow-x-auto">
                  <table className="rz-table">
                    <thead>
                      <tr>
                        <th>Request</th>
                        <th>Contractor</th>
                        <th>Milestone</th>
                        <th className="rz-num">Amount</th>
                        <th>State</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(
                        [
                          ['PR-14', 'Ashtrom', 'M6 · Frame, floor 6', 412800, 'held'],
                          ['PR-13', 'Electra', 'M5 · MEP rough-in', 188200, 'approved'],
                          ['PR-12', 'Solel Boneh', 'M4 · Frame, floor 5', 415000, 'rejected'],
                        ] as const
                      ).map(([id, who, m, amt, st]) => (
                        <tr key={id}>
                          <td className="font-medium">{id}</td>
                          <td>{who}</td>
                          <td className="text-muted-foreground">{m}</td>
                          <td className={st === 'rejected' ? 'rz-num rz-redline' : 'rz-num'}>
                            {ILS.format(amt)}
                          </td>
                          <td>
                            <Badge
                              tone={
                                st === 'held' ? 'accent' : st === 'approved' ? 'success' : 'danger'
                              }
                              dot={st === 'held'}
                            >
                              {st === 'held' ? 'Held' : st === 'approved' ? 'Approved' : 'Rejected'}
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
              <Panel title="Loading">
                <div className="grid gap-4">
                  <div className="rz-progress">
                    <div className="rz-progress__bar" style={{ ['--_v' as string]: '64%' }} />
                  </div>
                  <div className="rz-progress rz-progress--indeterminate">
                    <div className="rz-progress__bar" />
                  </div>
                  <div className="grid gap-2">
                    <Skeleton className="h-4 w-2/3" />
                    <Skeleton className="h-3 w-full" />
                    <Skeleton className="h-3 w-5/6" />
                  </div>
                </div>
              </Panel>
              <Panel title="Empty states">
                <EmptyState
                  art="approvals"
                  title="Nothing is waiting for you"
                  body="When an agent prepares a payment, a contract or a message to a client, it waits here for your decision."
                  action={<Button size="sm">See past decisions</Button>}
                />
              </Panel>
            </div>
          </Section>

          <Section
            id="overlays"
            title="Overlays"
            lede="Menus, dialogs, toasts and the command palette. Overlays are the only things with shadows."
          >
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => setDialog(true)}>Open dialog</Button>
              <Button
                onClick={() =>
                  toast.success('Payment request 14 approved. Ashtrom will be notified.')
                }
              >
                Success toast
              </Button>
              <Button
                onClick={() =>
                  toast.error(
                    'Couldn’t reach Google Drive. Check the connection in Integrations and try again.',
                  )
                }
              >
                Error toast
              </Button>
              <Button onClick={() => setPalette(true)}>
                <Search aria-hidden /> Command palette <Kbd>Ctrl K</Kbd>
              </Button>
              <span className="rz-btn rz-btn--ghost" data-tip="Tooltips wait 350ms, then rise 4px">
                Hover for a tooltip
              </span>
            </div>
            <div className="mt-6 rz-menu w-64" role="menu" aria-label="Example menu">
              <button className="rz-menu__item" role="menuitem">
                <FileText /> Open document
              </button>
              <button className="rz-menu__item" role="menuitem" data-active="true">
                <Inbox /> Move to project
              </button>
              <button className="rz-menu__item" role="menuitem">
                <CircleDot /> Mark as held
              </button>
              <div className="rz-menu__sep" />
              <button className="rz-menu__item rz-menu__item--danger" role="menuitem">
                <Trash2 /> Delete
              </button>
            </div>
          </Section>

          <Section
            id="field"
            title="Field language"
            lede="The parts only RealizeOS has. They come from the drawing set every architect, developer and site manager already reads."
          >
            <div className="grid gap-8">
              <div className="rz-panel p-5">
                <TitleBlock
                  crumbs={[
                    { label: 'Ventures', to: '/design#field' },
                    { label: 'Ramat Aviv Towers', to: '/design#field' },
                    { label: 'Approvals' },
                  ]}
                  title="Approvals"
                  description="Payments, contracts and messages your agents prepared. Nothing goes out until someone here decides."
                  reference={['Ramat Aviv Towers', 'Rev 14']}
                  actions={<Button variant="primary">Review held</Button>}
                />
                <p className="m-0 text-sm text-muted-foreground">
                  <strong className="text-foreground font-medium">Title block.</strong> The page
                  header follows a drawing sheet: where you are, what this sheet is, the scope it
                  covers and its revision.
                </p>
              </div>
              <div className="grid gap-8 lg:grid-cols-3">
                <div className="grid gap-3 content-start">
                  <div className="rz-panel rz-held p-4 ps-5 text-sm">
                    Investor report Q3 · waiting for Dana
                  </div>
                  <p className="m-0 text-sm text-muted-foreground">
                    <strong className="text-foreground font-medium">Held.</strong> Caution-tape
                    hatch on the leading edge. It drifts slowly so a held item reads as unfinished
                    from across the room.
                  </p>
                </div>
                <div className="grid gap-3 content-start">
                  <div className="flex gap-6 items-center h-[60px] px-2">
                    <Stamp decision="approved" by="Dana · 14:02" />
                    <Stamp decision="rejected" />
                    <Stamp decision="held" />
                  </div>
                  <p className="m-0 text-sm text-muted-foreground">
                    <strong className="text-foreground font-medium">Stamps.</strong> The decision
                    mark, double-ruled like a rubber stamp. It strikes only when a decision lands.
                  </p>
                </div>
                <div className="grid gap-3 content-start">
                  <p className="m-0 text-[15px] leading-relaxed">
                    The tender closes on 28 October
                    <SourceRef n={1} title="Tender 2026-118.pdf, p. 3" /> and the lowest bid is{' '}
                    <span className="rz-redline">₪8.4M</span>, 6% over budget
                    <SourceRef n={2} title="Budget v7.xlsx" />.
                  </p>
                  <p className="m-0 text-sm text-muted-foreground">
                    <strong className="text-foreground font-medium">Sources and redlines.</strong>{' '}
                    Every figure links to its document. A figure that fails a check is redlined,
                    like a plan revision.
                  </p>
                </div>
              </div>
            </div>
          </Section>

          <Section
            id="market"
            title="Market"
            lede="What the leading products do well, what Drawing Set takes from each, and what it leaves."
          >
            <div className="rz-panel overflow-x-auto">
              <table className="rz-table min-w-[760px]">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Known for</th>
                    <th>We take</th>
                    <th>We leave</th>
                  </tr>
                </thead>
                <tbody>
                  {MARKET.map(([name, known, take, leave]) => (
                    <tr key={name}>
                      <td className="font-medium whitespace-nowrap align-top py-3">{name}</td>
                      <td className="text-muted-foreground align-top py-3">{known}</td>
                      <td className="align-top py-3">{take}</td>
                      <td className="text-muted-foreground align-top py-3">{leave}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>
        </main>
      </div>

      <Dialog
        open={dialog}
        onClose={() => setDialog(false)}
        title="Delete Lisbon Riverside?"
        footer={
          <>
            <Button variant="ghost" onClick={() => setDialog(false)}>
              Keep venture
            </Button>
            <Button
              variant="danger"
              onClick={() => {
                setDialog(false)
                toast.success('Lisbon Riverside deleted')
              }}
            >
              <Trash2 aria-hidden /> Delete venture
            </Button>
          </>
        }
      >
        Its agents, skills and 214 documents will be removed from this server. The files in its
        FABRIC folder stay on disk, so you can bring it back.
      </Dialog>
      <CommandPalette commands={commands} open={palette} onOpenChange={setPalette} />
    </div>
  )
}
