/* eslint-disable react-refresh/only-export-components */
import { useState, useEffect } from 'react'
import {
  Bot,
  Brain,
  ArrowRight,
  ArrowLeft,
  Check,
  Eye,
  EyeOff,
  Loader2,
  Sparkles,
  Shield,
  Zap,
  Server,
  Search,
  Plug,
  Rocket,
} from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

const STORAGE_KEY = 'realizeos_onboarding_complete'

/** Check if onboarding has been completed */
export function isOnboardingComplete(): boolean {
  return localStorage.getItem(STORAGE_KEY) === 'true'
}

/** Mark onboarding as complete */
function markOnboardingComplete() {
  localStorage.setItem(STORAGE_KEY, 'true')
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

const LLM_PROVIDERS = [
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
    title: 'Multi-Agent System',
    description: 'Deploy specialized AI agents for different tasks',
  },
  {
    icon: Shield,
    title: 'Trust Ladder',
    description: 'Control what agents can do autonomously vs. with approval',
  },
  {
    icon: Zap,
    title: 'Smart Routing',
    description: 'Automatically route tasks to the best model for the job',
  },
  {
    icon: Search,
    title: 'Tools & Integrations',
    description: 'Web search, browser automation, Google Workspace, and more',
  },
]

// Step indicators
function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center gap-2">
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          className={cn(
            'h-2 rounded-full transition-all duration-300',
            i === current
              ? 'w-8 bg-brand-400'
              : i < current
              ? 'w-2 bg-brand-400/50'
              : 'w-2 bg-surface-600',
          )}
        />
      ))}
    </div>
  )
}

// Provider config card used in step 2
function ProviderInput({
  provider,
  configured,
  onSave,
}: {
  provider: (typeof LLM_PROVIDERS)[number]
  configured: boolean
  onSave: (id: string, value: string) => Promise<void>
}) {
  const [value, setValue] = useState('')
  const [showValue, setShowValue] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(configured)
  const Icon = provider.icon

  async function handleSave() {
    if (!value.trim()) return
    setSaving(true)
    try {
      await onSave(provider.id, value.trim())
      setSaved(true)
      setValue('')
    } catch {
      // silent
    } finally {
      setSaving(false)
    }
  }

  return (
    <div
      className={cn(
        'rounded-xl border p-4 transition-all duration-200',
        saved
          ? 'border-green-400/30 bg-green-400/5'
          : 'border-border bg-card hover:border-brand-400/30',
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'flex items-center justify-center w-10 h-10 rounded-lg shrink-0',
            saved ? 'bg-green-400/10' : 'bg-surface-700',
          )}
        >
          <Icon className={cn('h-5 w-5', saved ? 'text-green-400' : 'text-muted-foreground')} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-foreground">{provider.name}</h3>
            {provider.recommended && !saved && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-brand-400/10 text-brand-400 font-medium">
                Recommended
              </span>
            )}
            {saved && (
              <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-green-400/10 text-green-400 font-medium">
                <Check className="h-3 w-3" />
                Connected
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">{provider.description}</p>

          {!saved && (
            <div className="mt-3 space-y-2">
              <div className="relative">
                <input
                  type={showValue || provider.isUrl ? 'text' : 'password'}
                  value={value}
                  onChange={(e) => setValue(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && value.trim() && handleSave()}
                  placeholder={provider.help}
                  className="w-full rounded-lg border border-border bg-surface-800 px-3 py-2 pr-10 text-sm text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-brand-400"
                />
                {!provider.isUrl && (
                  <button
                    onClick={() => setShowValue(!showValue)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    type="button"
                  >
                    {showValue ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                )}
              </div>
              <button
                onClick={handleSave}
                disabled={saving || !value.trim()}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40 font-medium transition-colors"
              >
                {saving ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="h-3.5 w-3.5" />
                )}
                Connect
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function OnboardingWizard({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0)
  const [connectedProviders, setConnectedProviders] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)

  // On mount, check which providers are already configured
  useEffect(() => {
    async function checkExisting() {
      try {
        const data = await api.get<{ connections: Connection[] }>('/setup/connections')
        const configured = new Set<string>()
        for (const conn of data.connections) {
          if (conn.configured && ['anthropic', 'google_ai', 'openai', 'ollama'].includes(conn.id)) {
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

  async function handleProviderSave(id: string, value: string) {
    await api.put('/setup/connection', { id, value })
    setConnectedProviders((prev) => new Set([...prev, id]))
  }

  function handleFinish() {
    markOnboardingComplete()
    onComplete()
  }

  const totalSteps = 3 // Welcome, LLM Setup, Done
  const hasProvider = connectedProviders.size > 0

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 text-brand-400 animate-spin" />
      </div>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background overflow-y-auto">
      <div className="w-full max-w-2xl mx-auto p-6">
        {/* Step 0: Welcome */}
        {step === 0 && (
          <div className="text-center space-y-8 animate-in fade-in duration-500">
            {/* Logo */}
            <div className="flex items-center justify-center gap-3">
              <div className="flex items-center justify-center w-16 h-16 rounded-2xl bg-brand-400/10">
                <Bot className="h-9 w-9 text-brand-400" />
              </div>
            </div>

            <div>
              <h1 className="text-3xl font-bold text-foreground tracking-tight">
                Welcome to RealizeOS
              </h1>
              <p className="text-muted-foreground mt-2 max-w-md mx-auto">
                Your AI-powered operating system for business. Let's get you set up in under 2
                minutes.
              </p>
            </div>

            {/* Feature highlights */}
            <div className="grid grid-cols-2 gap-4 max-w-lg mx-auto text-left">
              {FEATURES.map((f) => (
                <div key={f.title} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4">
                  <f.icon className="h-5 w-5 text-brand-400 mt-0.5 shrink-0" />
                  <div>
                    <h3 className="text-sm font-semibold text-foreground">{f.title}</h3>
                    <p className="text-xs text-muted-foreground mt-0.5">{f.description}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-2">
              <button
                onClick={() => setStep(1)}
                className="inline-flex items-center gap-2 px-6 py-3 text-sm rounded-xl bg-brand-400 text-black hover:bg-brand-400/90 font-semibold transition-all hover:scale-[1.02] active:scale-[0.98]"
              >
                Get Started
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>

            <StepIndicator current={0} total={totalSteps} />
          </div>
        )}

        {/* Step 1: Connect LLM Provider */}
        {step === 1 && (
          <div className="space-y-6 animate-in fade-in duration-500">
            <div className="text-center">
              <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-brand-400/10 mx-auto mb-4">
                <Plug className="h-6 w-6 text-brand-400" />
              </div>
              <h2 className="text-2xl font-bold text-foreground">Connect an AI Provider</h2>
              <p className="text-muted-foreground mt-1 text-sm">
                RealizeOS needs at least one LLM provider to power your agents. Connect one or more
                below.
              </p>
            </div>

            <div className="space-y-3">
              {LLM_PROVIDERS.map((provider) => (
                <ProviderInput
                  key={provider.id}
                  provider={provider}
                  configured={connectedProviders.has(provider.id)}
                  onSave={handleProviderSave}
                />
              ))}
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                onClick={() => setStep(0)}
                className="flex items-center gap-1.5 px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
              >
                <ArrowLeft className="h-4 w-4" />
                Back
              </button>
              <div className="flex items-center gap-3">
                {!hasProvider && (
                  <span className="text-xs text-muted-foreground">
                    Connect at least one provider to continue
                  </span>
                )}
                <button
                  onClick={() => setStep(2)}
                  disabled={!hasProvider}
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-sm rounded-xl bg-brand-400 text-black hover:bg-brand-400/90 disabled:opacity-40 disabled:cursor-not-allowed font-semibold transition-all"
                >
                  Continue
                  <ArrowRight className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="flex justify-center">
              <StepIndicator current={1} total={totalSteps} />
            </div>
          </div>
        )}

        {/* Step 2: All Done */}
        {step === 2 && (
          <div className="text-center space-y-8 animate-in fade-in duration-500">
            <div className="flex items-center justify-center">
              <div className="relative">
                <div className="flex items-center justify-center w-20 h-20 rounded-full bg-green-400/10">
                  <Rocket className="h-10 w-10 text-green-400" />
                </div>
                <div className="absolute -top-1 -right-1 flex items-center justify-center w-7 h-7 rounded-full bg-green-400">
                  <Check className="h-4 w-4 text-black" />
                </div>
              </div>
            </div>

            <div>
              <h2 className="text-2xl font-bold text-foreground">You're All Set!</h2>
              <p className="text-muted-foreground mt-2 max-w-md mx-auto">
                RealizeOS is ready to go. You've connected{' '}
                <span className="text-foreground font-medium">
                  {connectedProviders.size} provider{connectedProviders.size !== 1 ? 's' : ''}
                </span>
                . You can add more integrations anytime from the Setup page.
              </p>
            </div>

            {/* Quick tips */}
            <div className="text-left max-w-md mx-auto space-y-3">
              <h3 className="text-sm font-semibold text-foreground">What to do next:</h3>
              <div className="space-y-2">
                {[
                  { label: 'Start a conversation', desc: 'Chat with your AI agents' },
                  { label: 'Explore Ventures', desc: 'See your business units and agents' },
                  { label: 'Configure Settings', desc: 'Adjust features, governance, and trust levels' },
                ].map((tip) => (
                  <div
                    key={tip.label}
                    className="flex items-start gap-3 rounded-lg border border-border bg-card p-3"
                  >
                    <Check className="h-4 w-4 text-green-400 mt-0.5 shrink-0" />
                    <div>
                      <span className="text-sm font-medium text-foreground">{tip.label}</span>
                      <span className="text-xs text-muted-foreground ml-1.5">— {tip.desc}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-2">
              <button
                onClick={handleFinish}
                className="inline-flex items-center gap-2 px-6 py-3 text-sm rounded-xl bg-brand-400 text-black hover:bg-brand-400/90 font-semibold transition-all hover:scale-[1.02] active:scale-[0.98]"
              >
                Go to Dashboard
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>

            <StepIndicator current={2} total={totalSteps} />
          </div>
        )}
      </div>
    </div>
  )
}
