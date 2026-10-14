/* eslint-disable react-refresh/only-export-components */
import { useState, useEffect, useId, useRef, type ReactNode, type Ref } from 'react'
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Brain,
  Check,
  Eye,
  EyeOff,
  Info,
  Languages,
  Search,
  Server,
  Shield,
  Sparkles,
  X,
  Zap,
} from 'lucide-react'
import { api } from '@/lib/api'
import { routingNameForSetupId } from '@/lib/llm-routing'
import { cn } from '@/lib/utils'
import { isUnrestricted, setupGate, type Actor } from '@/lib/permissions'
import { onboardingText, type OnboardingText, type ProviderId } from '@/lib/onboarding-text'
import { usePrefersReducedMotion } from '@/hooks/use-motion'
import { useLocale } from '@/components/locale-provider'
import { Badge } from '@/components/ui/badge'
import { BrandMark } from '@/components/ui/brand-mark'
import { Button, IconButton } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import { TitleBlock } from '@/components/ui/title-block'
import { Trail, type TrailStep } from '@/components/ui/trail'

const STORAGE_KEY = 'realizeos_onboarding_complete'

/** Check if onboarding has been completed in this browser */
export function isOnboardingComplete(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

/** Mark onboarding as complete in this browser */
export function markOnboardingComplete() {
  try {
    localStorage.setItem(STORAGE_KEY, 'true')
  } catch {
    // storage unavailable: the server-side check still skips the wizard next time
  }
}

/**
 * True when the server already has an AI provider configured (onboarding was
 * done). The "llm" category also holds routing settings (primary, tier
 * models), which are not providers; a row that names its `id` counts only
 * when it is one of the providers the wizard connects.
 */
export function serverHasAiProvider(
  connections: { id?: string; category: string; configured: boolean }[],
) {
  return connections.some(
    (c) =>
      c.category === 'llm' &&
      c.configured &&
      (c.id === undefined || LLM_PROVIDERS.some((p) => p.id === c.id)),
  )
}

/**
 * What the server said about setup: `done` (an AI provider is connected),
 * `needed`, or `unreachable` (the check failed); `unknown` until it answers.
 */
export type ServerSetup = 'unknown' | 'done' | 'needed' | 'unreachable'

/**
 * What a signed-in person gets on a server without an AI provider. Only
 * someone who may connect providers (`setupGate`: system:manage and every
 * venture) gets the wizard, since saving a key needs that; anyone else with
 * every venture gets a notice that an owner or admin must do it. A person
 * limited to some ventures gets neither (they can't read the setup state).
 */
export function onboardingPrompt(
  user: Actor | null | undefined,
  serverSetup: ServerSetup,
): 'wizard' | 'notice' | null {
  if (!user || !isUnrestricted(user)) return null
  if (setupGate(user) === null) {
    // A failed check still offers the wizard, as before: it re-reads the state itself.
    return serverSetup === 'needed' || serverSetup === 'unreachable' ? 'wizard' : null
  }
  return serverSetup === 'needed' ? 'notice' : null
}

const NOTICE_DISMISSED_KEY = 'realizeos_provider_notice_dismissed'

/** True when the person closed the "no AI provider yet" notice in this browser. */
export function isProviderNoticeDismissed(): boolean {
  try {
    return localStorage.getItem(NOTICE_DISMISSED_KEY) === 'true'
  } catch {
    return false
  }
}

/** Remember that the person closed the notice. */
export function dismissProviderNotice() {
  try {
    localStorage.setItem(NOTICE_DISMISSED_KEY, 'true')
  } catch {
    // storage unavailable: the notice stays closed for this page only
  }
}

/**
 * For someone who can't connect providers, on a server with none yet: who has
 * to do it. It can be closed; the dashboard works around it.
 */
export function ProviderNeededNotice({
  onDismiss,
  text: given,
}: {
  onDismiss: () => void
  text?: OnboardingText
}) {
  const text = useWizardText(given)
  return (
    <div
      role="status"
      data-notice="provider-needed"
      className="rz-panel mb-6 flex items-start gap-3 p-4 text-sm"
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="m-0 font-medium text-foreground">{text.providerNeededTitle}</p>
        <p className="m-0 mt-0.5 text-muted-foreground">{text.providerNeeded}</p>
      </div>
      <IconButton label={text.dismiss} size="sm" onClick={onDismiss}>
        <X />
      </IconButton>
    </div>
  )
}

/** What to tell the person when a provider key or URL could not be saved, in their language. */
export function saveErrorText(err: unknown, text: OnboardingText = onboardingText('en')): string {
  const detail = err instanceof Error ? err.message.trim() : ''
  return text.saveError(detail)
}

/**
 * The wizard's words: `text` when given (tests, a parent that already has
 * them), else the language in effect. Outside the locale provider that is
 * English.
 */
function useWizardText(text?: OnboardingText): OnboardingText {
  const { language } = useLocale()
  return text ?? onboardingText(language)
}

interface Connection {
  id: string
  name: string
  category: string
  env_key: string
  type: 'secret' | 'toggle' | 'url' | 'number' | 'text'
  configured: boolean
  masked_value: string | null
  description: string
  help: string
}

/** A provider the wizard can connect. Its description and help are in `OnboardingText`. */
export interface LlmProvider {
  id: ProviderId
  /** Product name: the same in every language. */
  name: string
  icon: typeof Brain
  /** The field is a server URL (shown as plain text), not a secret key. */
  isUrl?: boolean
  /** The field is a model id (LiteLLM), not a key. */
  isModel?: boolean
  /** Setup connection id of an optional second field: the gateway URL. */
  baseUrlId?: string
}

export const LLM_PROVIDERS: LlmProvider[] = [
  { id: 'anthropic', name: 'Claude (Anthropic)', icon: Brain },
  { id: 'google_ai', name: 'Gemini (Google)', icon: Brain },
  { id: 'openai', name: 'GPT-4 (OpenAI)', icon: Brain },
  { id: 'ollama', name: 'Ollama (Local)', icon: Server, isUrl: true },
  {
    id: 'litellm',
    name: 'LiteLLM (any other)',
    icon: Brain,
    isModel: true,
    baseUrlId: 'litellm_api_base',
  },
]

/** Icons for the four welcome lines, in `OnboardingText.features` order. */
const FEATURE_ICONS = [Sparkles, Shield, Zap, Search]

/** Welcome, connect a provider, done. */
export const TOTAL_STEPS = 3

/* ------------------------------------------------------------------ */
/* Pieces                                                              */
/* ------------------------------------------------------------------ */

/** The sheet reference for a step: scope and position, like "Setup · 2 of 3". */
function stepReference(step: number, text: OnboardingText): string[] {
  return [text.setup, text.stepOf(step + 1, TOTAL_STEPS)]
}

/** A survey line across the top of the sheet: how far through setup you are. */
function SetupProgress({ step, text }: { step: number; text: OnboardingText }) {
  const pct = `${Math.round(((step + 1) / TOTAL_STEPS) * 100)}%`
  return (
    <div
      className="rz-progress rounded-none"
      role="progressbar"
      aria-label={text.progressLabel}
      aria-valuemin={1}
      aria-valuemax={TOTAL_STEPS}
      aria-valuenow={step + 1}
      aria-valuetext={text.progressText(step + 1, TOTAL_STEPS)}
    >
      <div className="rz-progress__bar rounded-none" style={{ ['--_v' as string]: pct }} />
    </div>
  )
}

/** Step 1: what RealizeOS is, in four lines. */
export function WelcomeStep({ text: given }: { text?: OnboardingText } = {}) {
  const text = useWizardText(given)
  return (
    <>
      <TitleBlock
        title={text.welcomeTitle}
        description={text.welcomeDescription}
        reference={stepReference(0, text)}
      />
      <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2">
        {text.features.map((f, i) => {
          const Icon = FEATURE_ICONS[i] ?? Sparkles
          return (
            <li key={f.title} className="rz-card flex items-start gap-3">
              <span
                aria-hidden
                className="grid h-8 w-8 shrink-0 place-items-center rounded-[5px] bg-secondary text-muted-foreground"
              >
                <Icon className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <h3 className="m-0 text-sm font-semibold text-foreground">{f.title}</h3>
                <p className="m-0 mt-0.5 text-[13px] leading-snug text-muted-foreground">
                  {f.description}
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </>
  )
}

/** One provider: what it is, and a key (or URL) field to connect it. */
export function ProviderCard({
  provider,
  configured,
  onSave,
  text: given,
}: {
  provider: LlmProvider
  configured: boolean
  onSave: (id: string, value: string) => Promise<void>
  text?: OnboardingText
}) {
  const text = useWizardText(given)
  const [value, setValue] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [showValue, setShowValue] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(configured)
  const [error, setError] = useState('')
  const inputId = useId()
  const noteId = `${inputId}-note`
  const baseId = `${inputId}-base`
  const plain = provider.isUrl || provider.isModel
  const Icon = provider.icon
  const words = text.providers[provider.id]

  async function handleSave() {
    if (!value.trim()) return
    setSaving(true)
    setError('')
    try {
      await onSave(provider.id, value.trim())
      if (provider.baseUrlId && baseUrl.trim()) await onSave(provider.baseUrlId, baseUrl.trim())
      setSaved(true)
      setValue('')
      setBaseUrl('')
    } catch (err) {
      setError(saveErrorText(err, text))
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="rz-card grid gap-3">
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className={cn(
            'grid h-9 w-9 shrink-0 place-items-center rounded-[5px]',
            saved
              ? 'bg-[var(--rz-success-soft)] text-success'
              : 'bg-secondary text-muted-foreground',
          )}
        >
          <Icon className="h-[18px] w-[18px]" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="m-0 text-[15px] font-semibold text-foreground">
              <bdi>{provider.name}</bdi>
            </h3>
            {saved && (
              <Badge tone="success">
                <Check aria-hidden />
                {text.connected}
              </Badge>
            )}
          </div>
          <p className="m-0 mt-0.5 text-[13px] text-muted-foreground">{words.description}</p>
        </div>
      </div>

      {!saved && (
        <form
          className="rz-field"
          onSubmit={(e) => {
            e.preventDefault()
            void handleSave()
          }}
        >
          <label htmlFor={inputId} className="rz-label">
            {provider.isModel ? text.modelId : provider.isUrl ? text.serverUrl : text.apiKey}
          </label>
          <div className="flex gap-2">
            {/* Keys and URLs read left to right in every language: the field, its
                padding and the show/hide button share one direction, so in
                Hebrew the button never covers the start of the key. */}
            <div dir="ltr" className="relative min-w-0 flex-1">
              <input
                id={inputId}
                type={showValue || plain ? 'text' : 'password'}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={
                  provider.isModel
                    ? 'mistral/mistral-large-latest'
                    : provider.isUrl
                      ? 'http://localhost:11434'
                      : undefined
                }
                autoComplete="off"
                spellCheck={false}
                dir={provider.isModel ? 'auto' : 'ltr'}
                aria-describedby={noteId}
                aria-invalid={error ? true : undefined}
                className={cn('rz-input font-mono', !plain && 'pe-10', error && 'rz-nudge')}
              />
              {!plain && (
                <IconButton
                  label={showValue ? text.hideKey : text.showKey}
                  size="sm"
                  className="absolute end-[3px] top-1/2 -translate-y-1/2"
                  onClick={() => setShowValue(!showValue)}
                >
                  {showValue ? <EyeOff /> : <Eye />}
                </IconButton>
              )}
            </div>
            <Button type="submit" busy={saving} disabled={!value.trim()}>
              <Check aria-hidden />
              {text.connect}
            </Button>
          </div>
          {provider.baseUrlId && (
            <>
              <label htmlFor={baseId} className="rz-label mt-2">
                {text.apiBaseOptional}
              </label>
              <input
                id={baseId}
                type="text"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="http://localhost:4000"
                autoComplete="off"
                spellCheck={false}
                dir="ltr"
                className="rz-input font-mono"
              />
            </>
          )}
          {error ? (
            <span id={noteId} className="rz-error" role="alert">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {error}
            </span>
          ) : (
            <span id={noteId} className="rz-help">
              {words.help}
            </span>
          )}
        </form>
      )}
    </li>
  )
}

/**
 * Which connected provider answers first. "Automatic" (the default) leaves
 * it to the server; a choice is saved at once as the routing's primary.
 */
export function PrimaryProviderChoice({
  connected,
  value,
  onChoose,
  text: given,
}: {
  connected: LlmProvider[]
  value: string
  /** Save the choice (a routing provider name, or "" for automatic). */
  onChoose: (primary: string) => Promise<void>
  text?: OnboardingText
}) {
  const text = useWizardText(given)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const id = useId()
  const noteId = `${id}-note`

  async function choose(next: string) {
    setError('')
    setSaved(false)
    try {
      await onChoose(next)
      setSaved(true)
    } catch (err) {
      const detail = err instanceof Error ? err.message.trim() : ''
      setError(text.primaryError(detail))
    }
  }

  return (
    <div className="rz-card mt-4 grid gap-2" data-choice="primary-provider">
      <label htmlFor={id} className="rz-label">
        {text.primaryTitle}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => void choose(e.target.value)}
        aria-describedby={noteId}
        aria-invalid={error ? true : undefined}
        className="rz-select"
      >
        <option value="">{text.primaryAuto}</option>
        {connected.map((p) => (
          <option key={p.id} value={routingNameForSetupId(p.id)}>
            {p.name}
          </option>
        ))}
      </select>
      {error ? (
        <span id={noteId} className="rz-error" role="alert">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          {error}
        </span>
      ) : (
        <span id={noteId} className="rz-help" role="status">
          {saved ? text.primarySaved : text.primaryHelp}
        </span>
      )}
    </div>
  )
}

/** Step 2: connect at least one AI provider, then pick the primary one. */
export function ConnectStep({
  connected,
  onSave,
  primary = '',
  onPrimary,
  text: given,
}: {
  connected: Set<string>
  onSave: (id: string, value: string) => Promise<void>
  primary?: string
  onPrimary?: (primary: string) => Promise<void>
  text?: OnboardingText
}) {
  const text = useWizardText(given)
  const configured = LLM_PROVIDERS.filter((p) => connected.has(p.id))
  return (
    <>
      <TitleBlock
        title={text.connectTitle}
        description={text.connectDescription}
        reference={stepReference(1, text)}
      />
      <ul className="m-0 grid list-none gap-3 p-0">
        {LLM_PROVIDERS.map((provider) => (
          <ProviderCard
            key={provider.id}
            provider={provider}
            configured={connected.has(provider.id)}
            onSave={onSave}
            text={text}
          />
        ))}
      </ul>
      {onPrimary && configured.length > 0 && (
        <PrimaryProviderChoice
          connected={configured}
          value={primary}
          onChoose={onPrimary}
          text={text}
        />
      )}
    </>
  )
}

/** A check that draws itself once, when setup finishes. Still on reduced motion. */
function DoneMark({ animate }: { animate: boolean }) {
  return (
    <span
      aria-hidden
      className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[var(--rz-success-soft)] text-success"
    >
      <svg
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path
          d="M5 12.5l4.5 4.5L19 7.5"
          strokeDasharray="21"
          style={
            animate
              ? {
                  animation: 'rz-draw 560ms var(--rz-ease-out) 120ms both',
                  ['--rz-draw-length' as string]: 21,
                }
              : undefined
          }
        />
      </svg>
    </span>
  )
}

/** Step 3: what was set up, and what to do next, on one leader line. */
export function DoneStep({
  providers,
  animate,
  text: given,
}: {
  providers: string[]
  animate: boolean
  text?: OnboardingText
}) {
  const text = useWizardText(given)
  const count = providers.length
  const steps: TrailStep[] = [
    ...providers.map((name) => ({
      id: `connected-${name}`,
      state: 'done' as const,
      title: text.connectedProvider(name),
    })),
    ...text.nextSteps.map((tip, i) => ({
      id: `next-${i}`,
      state: 'pending' as const,
      title: tip.title,
      meta: tip.description,
    })),
  ]
  return (
    <>
      <TitleBlock
        title={
          <span className="inline-flex items-center gap-3">
            <DoneMark animate={animate} />
            {text.doneTitle}
          </span>
        }
        description={
          <>
            {text.doneBefore}{' '}
            <span className="font-medium text-foreground">{text.providerCount(count)}</span>
            {text.doneAfter}
          </>
        }
        reference={stepReference(2, text)}
      />
      <h2 className="m-0 mb-2 text-sm font-medium text-muted-foreground">{text.nextTitle}</h2>
      <Trail steps={steps} label={text.trailLabel} />
    </>
  )
}

/**
 * The drawing sheet every step sits on: brand, progress, the step, and its
 * actions. It carries the language and direction itself, so it reads right
 * whether or not the page around it has switched yet.
 */
export function WizardSheet({
  step,
  footer,
  children,
  stepRef,
  enterClass,
  headerEnd,
  text: given,
}: {
  step: number
  footer: ReactNode
  children: ReactNode
  stepRef?: Ref<HTMLDivElement>
  enterClass?: string
  /** Controls at the inline end of the brand row (the language button). */
  headerEnd?: ReactNode
  text?: OnboardingText
}) {
  const text = useWizardText(given)
  return (
    <div
      lang={text.lang}
      dir={text.dir}
      className="relative z-10 mx-auto flex min-h-full w-full max-w-2xl flex-col justify-center px-4 py-8 sm:py-12"
    >
      <div className="mb-5 flex items-center gap-3">
        <BrandMark size={24} />
        {headerEnd && <div className="ms-auto">{headerEnd}</div>}
      </div>
      <Panel
        flush
        className="overflow-hidden"
        style={{ boxShadow: 'var(--rz-shadow-3)' }}
        footer={footer}
      >
        <SetupProgress step={step} text={text} />
        <div
          key={step}
          ref={stepRef}
          tabIndex={-1}
          className={cn('p-5 outline-none sm:p-8', enterClass)}
        >
          {children}
        </div>
      </Panel>
    </div>
  )
}

/** Switch the wizard (and the dashboard after it) to the other language. */
export function WizardLanguageButton({
  text,
  onSwitch,
}: {
  text: OnboardingText
  onSwitch: (language: OnboardingText['switchTarget']) => void
}) {
  return (
    <Button
      variant="ghost"
      size="sm"
      aria-label={text.switchLabel}
      onClick={() => onSwitch(text.switchTarget)}
    >
      <Languages aria-hidden />
      <span lang={text.switchTarget}>{text.switchTo}</span>
    </Button>
  )
}

/* ------------------------------------------------------------------ */
/* Wizard                                                              */
/* ------------------------------------------------------------------ */

export default function OnboardingWizard({ onComplete }: { onComplete: () => void }) {
  const { language, setOverride } = useLocale()
  const text = onboardingText(language)
  const [step, setStep] = useState(0)
  const [connectedProviders, setConnectedProviders] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [primary, setPrimary] = useState('')
  const reduced = usePrefersReducedMotion()
  const scrollRef = useRef<HTMLDivElement>(null)
  const stepRef = useRef<HTMLDivElement>(null)
  const firstStep = useRef(true)

  // On mount, check which providers are already configured
  useEffect(() => {
    async function checkExisting() {
      try {
        const data = await api.get<{ connections: Connection[] }>('/setup/connections')
        const configured = new Set<string>()
        for (const conn of data.connections) {
          if (conn.configured && LLM_PROVIDERS.some((p) => p.id === conn.id)) {
            configured.add(conn.id)
          }
        }
        setConnectedProviders(configured)
      } catch {
        // API not available yet
      } finally {
        setLoading(false)
      }
    }
    checkExisting()
  }, [])

  // A new step starts at the top, and screen readers land on it
  useEffect(() => {
    if (loading) return
    if (firstStep.current) {
      firstStep.current = false
      return
    }
    scrollRef.current?.scrollTo({ top: 0 })
    stepRef.current?.focus({ preventScroll: true })
  }, [step, loading])

  async function handleProviderSave(id: string, value: string) {
    await api.put('/setup/connection', { id, value })
    // A second field of a provider (the LiteLLM gateway URL) is not a provider itself.
    if (LLM_PROVIDERS.some((p) => p.id === id)) {
      setConnectedProviders((prev) => new Set([...prev, id]))
    }
  }

  async function handlePrimary(choice: string) {
    await api.put('/llm/routing', { primary: choice })
    setPrimary(choice)
  }

  function handleFinish() {
    markOnboardingComplete()
    onComplete()
  }

  const hasProvider = connectedProviders.size > 0

  if (loading) {
    return (
      <div
        lang={text.lang}
        dir={text.dir}
        className="fixed inset-0 z-50 grid place-items-center bg-background"
        role="status"
        aria-label={text.loading}
      >
        <div className="grid w-48 justify-items-center gap-4">
          <BrandMark size={28} />
          <div className="rz-progress rz-progress--indeterminate w-full">
            <div className="rz-progress__bar" />
          </div>
        </div>
      </div>
    )
  }

  const footer =
    step === 0 ? (
      <div className="flex justify-end">
        <Button variant="primary" onClick={() => setStep(1)}>
          {text.getStarted}
          <ArrowRight className="rtl:rotate-180" aria-hidden />
        </Button>
      </div>
    ) : step === 1 ? (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button variant="ghost" className="-ms-2" onClick={() => setStep(0)}>
          <ArrowLeft className="rtl:rotate-180" aria-hidden />
          {text.back}
        </Button>
        <div className="ms-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
          {!hasProvider && (
            <span className="text-xs text-subtle-foreground">{text.needProvider}</span>
          )}
          <Button variant="primary" onClick={() => setStep(2)} disabled={!hasProvider}>
            {text.continue}
            <ArrowRight className="rtl:rotate-180" aria-hidden />
          </Button>
        </div>
      </div>
    ) : (
      <div className="flex justify-end">
        <Button variant="primary" onClick={handleFinish}>
          {text.finish}
          <ArrowRight className="rtl:rotate-180" aria-hidden />
        </Button>
      </div>
    )

  return (
    <div
      ref={scrollRef}
      lang={text.lang}
      dir={text.dir}
      className="fixed inset-0 z-50 overflow-y-auto bg-background"
    >
      {/* The drafting grid fades out from the centre: the one ambient surface */}
      <div
        aria-hidden
        className="rz-drafting-grid pointer-events-none fixed inset-0 [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_70%)]"
      />
      <WizardSheet
        step={step}
        footer={footer}
        stepRef={stepRef}
        enterClass={reduced ? 'rz-fade' : 'rz-enter'}
        headerEnd={<WizardLanguageButton text={text} onSwitch={setOverride} />}
        text={text}
      >
        {step === 0 && <WelcomeStep text={text} />}
        {step === 1 && (
          <ConnectStep
            connected={connectedProviders}
            onSave={handleProviderSave}
            primary={primary}
            onPrimary={handlePrimary}
            text={text}
          />
        )}
        {step === 2 && (
          <DoneStep
            providers={LLM_PROVIDERS.filter((p) => connectedProviders.has(p.id)).map((p) => p.name)}
            animate={!reduced}
            text={text}
          />
        )}
      </WizardSheet>
    </div>
  )
}
