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
  Search,
  Server,
  Shield,
  Sparkles,
  Zap,
} from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { usePrefersReducedMotion } from '@/hooks/use-motion'
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

/** True when the server already has an AI provider configured (onboarding was done). */
export function serverHasAiProvider(connections: { category: string; configured: boolean }[]) {
  return connections.some((c) => c.category === 'llm' && c.configured)
}

/** What to tell the person when a provider key or URL could not be saved. */
export function saveErrorText(err: unknown): string {
  const detail = err instanceof Error ? err.message.trim() : ''
  return detail ? `Couldn’t connect: ${detail}` : 'Couldn’t connect. Check the value and try again.'
}

interface Connection {
  id: string
  name: string
  category: string
  env_key: string
  type: 'secret' | 'toggle' | 'url' | 'number'
  configured: boolean
  masked_value: string | null
  description: string
  help: string
}

export interface LlmProvider {
  id: string
  name: string
  icon: typeof Brain
  description: string
  help: string
  recommended: boolean
  isUrl?: boolean
}

export const LLM_PROVIDERS: LlmProvider[] = [
  {
    id: 'anthropic',
    name: 'Claude (Anthropic)',
    icon: Brain,
    description: 'Best for complex reasoning, writing, and code',
    help: 'Get your key at console.anthropic.com',
    recommended: true,
  },
  {
    id: 'google_ai',
    name: 'Gemini (Google)',
    icon: Brain,
    description: 'Fast and cost-effective for most tasks',
    help: 'Get your key at aistudio.google.com',
    recommended: false,
  },
  {
    id: 'openai',
    name: 'GPT-4 (OpenAI)',
    icon: Brain,
    description: 'Strong general-purpose AI models',
    help: 'Get your key at platform.openai.com',
    recommended: false,
  },
  {
    id: 'ollama',
    name: 'Ollama (Local)',
    icon: Server,
    description: 'Run models locally — free, private, no API key',
    help: 'Default URL: http://localhost:11434',
    recommended: false,
    isUrl: true,
  },
]

const FEATURES = [
  {
    icon: Sparkles,
    title: 'Multi-agent system',
    description: 'Deploy specialized AI agents for different tasks',
  },
  {
    icon: Shield,
    title: 'Trust ladder',
    description: 'Control what agents can do autonomously vs. with approval',
  },
  {
    icon: Zap,
    title: 'Smart routing',
    description: 'Automatically route tasks to the best model for the job',
  },
  {
    icon: Search,
    title: 'Tools and integrations',
    description: 'Web search, browser automation, Google Workspace, and more',
  },
]

const NEXT_STEPS = [
  { label: 'Start a conversation', desc: 'Chat with your AI agents' },
  { label: 'Explore ventures', desc: 'See your business units and agents' },
  { label: 'Configure settings', desc: 'Adjust features, governance, and trust levels' },
]

/** Welcome, connect a provider, done. */
export const TOTAL_STEPS = 3

/* ------------------------------------------------------------------ */
/* Pieces                                                              */
/* ------------------------------------------------------------------ */

/** The sheet reference for a step: scope and position, like "Setup · 2 of 3". */
function stepReference(step: number): string[] {
  return ['Setup', `${step + 1} of ${TOTAL_STEPS}`]
}

/** A survey line across the top of the sheet: how far through setup you are. */
function SetupProgress({ step }: { step: number }) {
  const pct = `${Math.round(((step + 1) / TOTAL_STEPS) * 100)}%`
  return (
    <div
      className="rz-progress rounded-none"
      role="progressbar"
      aria-label="Setup progress"
      aria-valuemin={1}
      aria-valuemax={TOTAL_STEPS}
      aria-valuenow={step + 1}
      aria-valuetext={`Step ${step + 1} of ${TOTAL_STEPS}`}
    >
      <div className="rz-progress__bar rounded-none" style={{ ['--_v' as string]: pct }} />
    </div>
  )
}

/** Step 1: what RealizeOS is, in four lines. */
export function WelcomeStep() {
  return (
    <>
      <TitleBlock
        title="Welcome to RealizeOS"
        description="Your AI-powered operating system for business. Let’s get you set up in under 2 minutes."
        reference={stepReference(0)}
      />
      <ul className="m-0 grid list-none gap-3 p-0 sm:grid-cols-2">
        {FEATURES.map((f) => (
          <li key={f.title} className="rz-card flex items-start gap-3">
            <span
              aria-hidden
              className="grid h-8 w-8 shrink-0 place-items-center rounded-[5px] bg-secondary text-muted-foreground"
            >
              <f.icon className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h3 className="m-0 text-sm font-semibold text-foreground">{f.title}</h3>
              <p className="m-0 mt-0.5 text-[13px] leading-snug text-muted-foreground">
                {f.description}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </>
  )
}

/** One provider: what it is, and a key (or URL) field to connect it. */
export function ProviderCard({
  provider,
  configured,
  onSave,
}: {
  provider: LlmProvider
  configured: boolean
  onSave: (id: string, value: string) => Promise<void>
}) {
  const [value, setValue] = useState('')
  const [showValue, setShowValue] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(configured)
  const [error, setError] = useState('')
  const inputId = useId()
  const noteId = `${inputId}-note`
  const Icon = provider.icon

  async function handleSave() {
    if (!value.trim()) return
    setSaving(true)
    setError('')
    try {
      await onSave(provider.id, value.trim())
      setSaved(true)
      setValue('')
    } catch (err) {
      setError(saveErrorText(err))
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
            <h3 className="m-0 text-[15px] font-semibold text-foreground">{provider.name}</h3>
            {provider.recommended && !saved && <Badge tone="accent">Recommended</Badge>}
            {saved && (
              <Badge tone="success">
                <Check aria-hidden />
                Connected
              </Badge>
            )}
          </div>
          <p className="m-0 mt-0.5 text-[13px] text-muted-foreground">{provider.description}</p>
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
            {provider.isUrl ? 'Server URL' : 'API key'}
          </label>
          <div className="flex gap-2">
            <div className="relative min-w-0 flex-1">
              <input
                id={inputId}
                type={showValue || provider.isUrl ? 'text' : 'password'}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={provider.isUrl ? 'http://localhost:11434' : undefined}
                autoComplete="off"
                spellCheck={false}
                dir="ltr"
                aria-describedby={noteId}
                aria-invalid={error ? true : undefined}
                className={cn(
                  'rz-input font-mono',
                  !provider.isUrl && 'pe-10',
                  error && 'rz-nudge',
                )}
              />
              {!provider.isUrl && (
                <IconButton
                  label={showValue ? 'Hide key' : 'Show key'}
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
              Connect
            </Button>
          </div>
          {error ? (
            <span id={noteId} className="rz-error" role="alert">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {error}
            </span>
          ) : (
            <span id={noteId} className="rz-help">
              {provider.help}
            </span>
          )}
        </form>
      )}
    </li>
  )
}

/** Step 2: connect at least one AI provider. */
export function ConnectStep({
  connected,
  onSave,
}: {
  connected: Set<string>
  onSave: (id: string, value: string) => Promise<void>
}) {
  return (
    <>
      <TitleBlock
        title="Connect an AI provider"
        description="RealizeOS needs at least one LLM provider to power your agents. Connect one or more below."
        reference={stepReference(1)}
      />
      <ul className="m-0 grid list-none gap-3 p-0">
        {LLM_PROVIDERS.map((provider) => (
          <ProviderCard
            key={provider.id}
            provider={provider}
            configured={connected.has(provider.id)}
            onSave={onSave}
          />
        ))}
      </ul>
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
export function DoneStep({ providers, animate }: { providers: string[]; animate: boolean }) {
  const count = providers.length
  const steps: TrailStep[] = [
    ...providers.map((name) => ({
      id: `connected-${name}`,
      state: 'done' as const,
      title: `Connected ${name}`,
    })),
    ...NEXT_STEPS.map((tip) => ({
      id: `next-${tip.label}`,
      state: 'pending' as const,
      title: tip.label,
      meta: tip.desc,
    })),
  ]
  return (
    <>
      <TitleBlock
        title={
          <span className="inline-flex items-center gap-3">
            <DoneMark animate={animate} />
            You’re all set
          </span>
        }
        description={
          <>
            RealizeOS is ready to go. You’ve connected{' '}
            <span className="font-medium text-foreground">
              {count} provider{count !== 1 ? 's' : ''}
            </span>
            . You can add more integrations anytime from the Setup page.
          </>
        }
        reference={stepReference(2)}
      />
      <h2 className="m-0 mb-2 text-sm font-medium text-muted-foreground">What to do next</h2>
      <Trail steps={steps} label="Setup and next steps" />
    </>
  )
}

/** The drawing sheet every step sits on: brand, progress, the step, and its actions. */
export function WizardSheet({
  step,
  footer,
  children,
  stepRef,
  enterClass,
}: {
  step: number
  footer: ReactNode
  children: ReactNode
  stepRef?: Ref<HTMLDivElement>
  enterClass?: string
}) {
  return (
    <div className="relative z-10 mx-auto flex min-h-full w-full max-w-2xl flex-col justify-center px-4 py-8 sm:py-12">
      <div className="mb-5 flex items-center">
        <BrandMark size={24} />
      </div>
      <Panel
        flush
        className="overflow-hidden"
        style={{ boxShadow: 'var(--rz-shadow-3)' }}
        footer={footer}
      >
        <SetupProgress step={step} />
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

/* ------------------------------------------------------------------ */
/* Wizard                                                              */
/* ------------------------------------------------------------------ */

export default function OnboardingWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0)
  const [connectedProviders, setConnectedProviders] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
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
    setConnectedProviders((prev) => new Set([...prev, id]))
  }

  function handleFinish() {
    markOnboardingComplete()
    onComplete()
  }

  const hasProvider = connectedProviders.size > 0

  if (loading) {
    return (
      <div
        className="fixed inset-0 z-50 grid place-items-center bg-background"
        role="status"
        aria-label="Loading setup"
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
          Get started
          <ArrowRight className="rtl:rotate-180" aria-hidden />
        </Button>
      </div>
    ) : step === 1 ? (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Button variant="ghost" className="-ms-2" onClick={() => setStep(0)}>
          <ArrowLeft className="rtl:rotate-180" aria-hidden />
          Back
        </Button>
        <div className="ms-auto flex flex-wrap items-center justify-end gap-x-3 gap-y-2">
          {!hasProvider && (
            <span className="text-xs text-subtle-foreground">
              Connect at least one provider to continue
            </span>
          )}
          <Button variant="primary" onClick={() => setStep(2)} disabled={!hasProvider}>
            Continue
            <ArrowRight className="rtl:rotate-180" aria-hidden />
          </Button>
        </div>
      </div>
    ) : (
      <div className="flex justify-end">
        <Button variant="primary" onClick={handleFinish}>
          Go to dashboard
          <ArrowRight className="rtl:rotate-180" aria-hidden />
        </Button>
      </div>
    )

  return (
    <div ref={scrollRef} className="fixed inset-0 z-50 overflow-y-auto bg-background">
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
      >
        {step === 0 && <WelcomeStep />}
        {step === 1 && <ConnectStep connected={connectedProviders} onSave={handleProviderSave} />}
        {step === 2 && (
          <DoneStep
            providers={LLM_PROVIDERS.filter((p) => connectedProviders.has(p.id)).map((p) => p.name)}
            animate={!reduced}
          />
        )}
      </WizardSheet>
    </div>
  )
}
