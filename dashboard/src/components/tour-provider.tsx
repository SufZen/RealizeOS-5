import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { X, ChevronLeft, ChevronRight, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface TourStep {
  /** CSS selector for the target element to highlight */
  target: string
  /** Step title */
  title: string
  /** Step description */
  description: string
  /** Preferred popover position */
  position?: 'top' | 'bottom' | 'left' | 'right'
  /** Optional: navigate to this path before showing step */
  path?: string
}

interface TourCtx {
  isRunning: boolean
  currentStep: number
  totalSteps: number
  startTour: () => void
  endTour: () => void
}

const STORAGE_KEY = 'realizeos_tour_complete'

/* ------------------------------------------------------------------ */
/* Default 15-step tour                                                */
/* ------------------------------------------------------------------ */

export const DEFAULT_TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour="sidebar"]',
    title: 'Welcome to RealizeOS! 👋',
    description: 'This is your navigation sidebar. It\u2019s organized into four groups: Core, Build, Monitor, and Configure. Let\u2019s walk through the first steps of using the system.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-overview"]',
    title: '1. Dashboard Overview',
    description: 'Start here. The Overview page gives you a snapshot of all your ventures, agents, and recent activity in one place.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-chat"]',
    title: '2. Chat with Your AI',
    description: 'Talk to your AI agents in natural language. Issue commands, ask questions, or delegate tasks — this is your primary interface.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-ventures"]',
    title: '3. Manage Ventures',
    description: 'Ventures are your business units or projects. Each venture has its own agents, skills, and knowledge base. Create your first venture here.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-skills"]',
    title: '4. Install Skills',
    description: 'Skills are pre-built capabilities for your agents — like email drafting, research, or scheduling. Browse the library and install what you need.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-pipelines"]',
    title: '5. Build Pipelines',
    description: 'Chain multiple agents and tools into automated workflows. Pipelines let you build complex multi-step processes visually.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-workflows"]',
    title: '6. Create Workflows',
    description: 'Define YAML-based workflow templates that your agents can execute. Great for repeatable business processes.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-activity"]',
    title: '7. Monitor Activity',
    description: 'See everything your agents are doing in real-time. Track actions, outputs, and status across all ventures.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-approvals"]',
    title: '8. Review Approvals',
    description: 'When agents need human approval for sensitive actions (sending emails, API calls), requests appear here. You stay in control.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-evolution"]',
    title: '9. Track Evolution',
    description: 'Monitor how your agents improve over time. See performance metrics, learning patterns, and optimization suggestions.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-routing"]',
    title: '10. Configure Routing',
    description: 'Control which AI models handle which tasks. Set up intelligent routing rules based on cost, quality, or speed preferences.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-tools"]',
    title: '11. Manage Tools',
    description: 'Tools are integrations your agents can use — web search, browser, file management, and more. Enable or disable them here.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-integrations"]',
    title: '12. Connect Integrations',
    description: 'Link external services like Google Workspace, Slack, Stripe, and more. These let your agents interact with your business tools.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-setup"]',
    title: '13. Set Up Connections',
    description: 'Configure your AI provider API keys (OpenAI, Anthropic, Google) and other connection settings. This is essential to get started.',
    position: 'right',
  },
  {
    target: '[data-tour="nav-settings"]',
    title: '14. System Settings',
    description: 'Fine-tune system features like approval gates, heartbeats, auto-memory, and proactive mode. You can also manage databases and providers.',
    position: 'right',
  },
  {
    target: '[data-tour="theme-toggle"]',
    title: '15. Customize Your Theme',
    description: 'Switch between Dark, Light, or System theme. Your preference is saved automatically. Enjoy using RealizeOS! 🚀',
    position: 'right',
  },
]

/* ------------------------------------------------------------------ */
/* Context                                                             */
/* ------------------------------------------------------------------ */

const TourContext = createContext<TourCtx>({
  isRunning: false,
  currentStep: 0,
  totalSteps: 0,
  startTour: () => {},
  endTour: () => {},
})

export const useTour = () => useContext(TourContext)

/* ------------------------------------------------------------------ */
/* Provider                                                            */
/* ------------------------------------------------------------------ */

export function TourProvider({ children }: { children: ReactNode }) {
  const [isRunning, setIsRunning] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const steps = DEFAULT_TOUR_STEPS

  const startTour = useCallback(() => {
    setCurrentStep(0)
    setIsRunning(true)
  }, [])

  const endTour = useCallback(() => {
    setIsRunning(false)
    setCurrentStep(0)
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
    } catch {
      // ignore
    }
  }, [])

  const next = useCallback(() => {
    if (currentStep < steps.length - 1) {
      setCurrentStep((s) => s + 1)
    } else {
      endTour()
    }
  }, [currentStep, steps.length, endTour])

  const prev = useCallback(() => {
    if (currentStep > 0) setCurrentStep((s) => s - 1)
  }, [currentStep])

  // Auto-start on first visit
  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        // Small delay so the DOM settles after initial render
        const t = setTimeout(() => setIsRunning(true), 1200)
        return () => clearTimeout(t)
      }
    } catch {
      // ignore
    }
  }, [])

  return (
    <TourContext.Provider value={{ isRunning, currentStep, totalSteps: steps.length, startTour, endTour }}>
      {children}
      {isRunning && (
        <TourOverlay
          step={steps[currentStep]}
          stepIndex={currentStep}
          totalSteps={steps.length}
          onNext={next}
          onPrev={prev}
          onSkip={endTour}
        />
      )}
    </TourContext.Provider>
  )
}

/* ------------------------------------------------------------------ */
/* Overlay / Spotlight                                                 */
/* ------------------------------------------------------------------ */

interface TourOverlayProps {
  step: TourStep
  stepIndex: number
  totalSteps: number
  onNext: () => void
  onPrev: () => void
  onSkip: () => void
}

function TourOverlay({ step, stepIndex, totalSteps, onNext, onPrev, onSkip }: TourOverlayProps) {
  const [rect, setRect] = useState<DOMRect | null>(null)

  useEffect(() => {
    const el = document.querySelector(step.target)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      // Allow scroll to settle
      const t = setTimeout(() => setRect(el.getBoundingClientRect()), 150)
      return () => clearTimeout(t)
    } else {
      setRect(null)
    }
  }, [step.target])

  // Recalculate on resize
  useEffect(() => {
    const handler = () => {
      const el = document.querySelector(step.target)
      if (el) setRect(el.getBoundingClientRect())
    }
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [step.target])

  const isLast = stepIndex === totalSteps - 1
  const pad = 8

  // Popover positioning
  const popoverStyle: React.CSSProperties = {}
  if (rect) {
    const pos = step.position ?? 'right'
    if (pos === 'right') {
      popoverStyle.left = rect.right + pad + 12
      popoverStyle.top = rect.top + rect.height / 2
      popoverStyle.transform = 'translateY(-50%)'
    } else if (pos === 'left') {
      popoverStyle.right = window.innerWidth - rect.left + pad + 12
      popoverStyle.top = rect.top + rect.height / 2
      popoverStyle.transform = 'translateY(-50%)'
    } else if (pos === 'bottom') {
      popoverStyle.left = rect.left + rect.width / 2
      popoverStyle.top = rect.bottom + pad + 12
      popoverStyle.transform = 'translateX(-50%)'
    } else {
      popoverStyle.left = rect.left + rect.width / 2
      popoverStyle.bottom = window.innerHeight - rect.top + pad + 12
      popoverStyle.transform = 'translateX(-50%)'
    }
  } else {
    // Fallback: center screen
    popoverStyle.left = '50%'
    popoverStyle.top = '50%'
    popoverStyle.transform = 'translate(-50%, -50%)'
  }

  return createPortal(
    <>
      {/* SVG overlay with cutout */}
      <svg
        className="fixed inset-0 z-[9998] pointer-events-none"
        width="100%"
        height="100%"
        style={{ position: 'fixed', inset: 0 }}
      >
        <defs>
          <mask id="tour-mask">
            <rect x="0" y="0" width="100%" height="100%" fill="white" />
            {rect && (
              <rect
                x={rect.left - pad}
                y={rect.top - pad}
                width={rect.width + pad * 2}
                height={rect.height + pad * 2}
                rx="12"
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect
          x="0"
          y="0"
          width="100%"
          height="100%"
          fill="rgba(0,0,0,0.6)"
          mask="url(#tour-mask)"
        />
      </svg>

      {/* Spotlight border glow */}
      {rect && (
        <div
          className="fixed z-[9999] rounded-xl border-2 border-brand-400 pointer-events-none"
          style={{
            left: rect.left - pad,
            top: rect.top - pad,
            width: rect.width + pad * 2,
            height: rect.height + pad * 2,
            boxShadow: '0 0 0 4px rgba(255, 204, 0, 0.15), 0 0 24px rgba(255, 204, 0, 0.1)',
            transition: 'all 0.3s ease',
          }}
        />
      )}

      {/* Click-catcher behind popover */}
      <div className="fixed inset-0 z-[9999]" onClick={onSkip} />

      {/* Popover  */}
      <div
        className="fixed z-[10000] w-80 rounded-xl border border-border bg-card shadow-2xl p-5"
        style={popoverStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close */}
        <button
          onClick={onSkip}
          className="absolute top-3 right-3 p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>

        {/* Content */}
        <div className="flex items-center gap-2 mb-2">
          <Sparkles className="h-4 w-4 text-brand-400" />
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
            Step {stepIndex + 1} of {totalSteps}
          </span>
        </div>
        <h3 className="text-sm font-bold text-foreground mb-1.5">{step.title}</h3>
        <p className="text-xs text-muted-foreground leading-relaxed mb-4">{step.description}</p>

        {/* Progress dots */}
        <div className="flex items-center gap-1 mb-3">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <div
              key={i}
              className={cn(
                'h-1 rounded-full transition-all',
                i === stepIndex ? 'w-4 bg-brand-400' : i < stepIndex ? 'w-1.5 bg-brand-400/40' : 'w-1.5 bg-surface-700',
              )}
            />
          ))}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between">
          <button
            onClick={onSkip}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Skip tour
          </button>
          <div className="flex items-center gap-2">
            {stepIndex > 0 && (
              <button
                onClick={onPrev}
                className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-border text-foreground hover:bg-surface-700 transition-colors"
              >
                <ChevronLeft className="h-3 w-3" />
                Back
              </button>
            )}
            <button
              onClick={onNext}
              className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 font-medium transition-colors"
            >
              {isLast ? 'Finish' : 'Next'}
              {!isLast && <ChevronRight className="h-3 w-3" />}
            </button>
          </div>
        </div>
      </div>
    </>,
    document.body,
  )
}
