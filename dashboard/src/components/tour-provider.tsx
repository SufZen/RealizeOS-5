/* eslint-disable react-refresh/only-export-components, react-hooks/set-state-in-effect */
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useLayoutEffect,
  useCallback,
  useMemo,
  useRef,
  type ReactNode,
  type Ref,
} from 'react'
import { createPortal } from 'react-dom'
import { X, ChevronLeft, ChevronRight } from 'lucide-react'
import { useAuth } from '@/hooks/use-auth'
import { usePrefersReducedMotion } from '@/hooks/use-motion'
import { useLocale } from '@/components/locale-provider'
import { Button, IconButton } from '@/components/ui/button'
import { tourText, type TourStepId, type TourText } from '@/lib/tour-text'

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
  /**
   * Preferred popover side, as seen in a left-to-right layout. Left and right
   * mirror in RTL, so "right" always means the side away from the sidebar.
   */
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
/* Steps                                                               */
/* ------------------------------------------------------------------ */

/** Where each step points and which side it opens on; the words come from `tourText`. */
const TOUR_LAYOUT: { id: TourStepId; target: string; position: TourStep['position'] }[] = [
  { id: 'sidebar', target: '[data-tour="sidebar"]', position: 'right' },
  { id: 'overview', target: '[data-tour="nav-overview"]', position: 'right' },
  { id: 'chat', target: '[data-tour="nav-chat"]', position: 'right' },
  { id: 'ventures', target: '[data-tour="nav-ventures"]', position: 'right' },
  { id: 'skills', target: '[data-tour="nav-skills"]', position: 'right' },
  { id: 'pipelines', target: '[data-tour="nav-pipelines"]', position: 'right' },
  { id: 'workflows', target: '[data-tour="nav-workflows"]', position: 'right' },
  { id: 'activity', target: '[data-tour="nav-activity"]', position: 'right' },
  { id: 'approvals', target: '[data-tour="nav-approvals"]', position: 'right' },
  { id: 'evolution', target: '[data-tour="nav-evolution"]', position: 'right' },
  { id: 'routing', target: '[data-tour="nav-routing"]', position: 'right' },
  { id: 'tools', target: '[data-tour="nav-tools"]', position: 'right' },
  { id: 'integrations', target: '[data-tour="nav-integrations"]', position: 'right' },
  { id: 'setup', target: '[data-tour="nav-setup"]', position: 'right' },
  { id: 'settings', target: '[data-tour="nav-settings"]', position: 'right' },
  { id: 'theme', target: '[data-tour="theme-toggle"]', position: 'right' },
]

/** The tour in a language: the same steps, places and sides, in that language's words. */
export function tourSteps(language: string | null | undefined): TourStep[] {
  const text = tourText(language)
  return TOUR_LAYOUT.map(({ id, target, position }) => ({ target, position, ...text.steps[id] }))
}

export const DEFAULT_TOUR_STEPS: TourStep[] = tourSteps('en')

/* ------------------------------------------------------------------ */
/* Placement                                                           */
/* ------------------------------------------------------------------ */

export interface Box {
  left: number
  top: number
  width: number
  height: number
}

type Side = NonNullable<TourStep['position']>

/** Gap between the highlighted element and the popover. */
const GAP = 16
/** Closest the popover may come to the edge of the window. */
const EDGE = 12
/** How far the spotlight ring sits outside the highlighted element. */
const SPOT_PAD = 6

const OPPOSITE: Record<Side, Side> = { left: 'right', right: 'left', top: 'bottom', bottom: 'top' }

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(v, Math.max(min, max)))
}

/**
 * Where the tour popover goes, in window coordinates. Left and right mirror in
 * RTL (the sidebar is on the right there). If the preferred side has no room
 * it tries the opposite side, then below and above; the popover always stays
 * inside the window. A missing or hidden target (zero size, as on a phone where
 * the sidebar is folded away) centres the popover.
 */
export function placeTourPopover(
  target: Box | null,
  side: Side | undefined,
  popover: { width: number; height: number },
  viewport: { width: number; height: number },
  dir: 'ltr' | 'rtl' = 'ltr',
): { left: number; top: number } {
  const { width: w, height: h } = popover
  const maxLeft = viewport.width - w - EDGE
  const maxTop = viewport.height - h - EDGE

  if (!target || (target.width === 0 && target.height === 0)) {
    return {
      left: clamp((viewport.width - w) / 2, EDGE, maxLeft),
      top: clamp((viewport.height - h) / 2, EDGE, maxTop),
    }
  }

  let preferred: Side = side ?? 'right'
  if (dir === 'rtl' && (preferred === 'left' || preferred === 'right')) {
    preferred = OPPOSITE[preferred]
  }
  const t = target
  const at = (s: Side) => {
    if (s === 'right') return { left: t.left + t.width + GAP, top: t.top + t.height / 2 - h / 2 }
    if (s === 'left') return { left: t.left - GAP - w, top: t.top + t.height / 2 - h / 2 }
    if (s === 'bottom') return { left: t.left + t.width / 2 - w / 2, top: t.top + t.height + GAP }
    return { left: t.left + t.width / 2 - w / 2, top: t.top - GAP - h }
  }
  const fits = (s: Side, p: { left: number; top: number }) =>
    s === 'left' || s === 'right'
      ? p.left >= EDGE && p.left <= maxLeft
      : p.top >= EDGE && p.top <= maxTop

  const order: Side[] = [preferred, OPPOSITE[preferred], 'bottom', 'top']
  for (const s of order) {
    const p = at(s)
    if (fits(s, p)) return { left: clamp(p.left, EDGE, maxLeft), top: clamp(p.top, EDGE, maxTop) }
  }
  return {
    left: clamp((viewport.width - w) / 2, EDGE, maxLeft),
    top: clamp((viewport.height - h) / 2, EDGE, maxTop),
  }
}

/** The target's box, or null when it is missing or not on screen. */
function measure(selector: string): Box | null {
  const el = document.querySelector(selector)
  if (!el) return null
  const r = el.getBoundingClientRect()
  if (r.width === 0 && r.height === 0) return null
  return { left: r.left, top: r.top, width: r.width, height: r.height }
}

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

/**
 * The guided tour. It sits inside the locale provider, so it speaks the
 * person's language (Hebrew reads right to left) and follows a switch mid-tour.
 */
export function TourProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const { language } = useLocale()
  const [started, setStarted] = useState(false)
  // Never over the sign-in page: the tour belongs to the signed-in app shell.
  const isRunning = started && !!user
  const [currentStep, setCurrentStep] = useState(0)
  const steps = useMemo(() => tourSteps(language), [language])
  const text = tourText(language)

  const startTour = useCallback(() => {
    setCurrentStep(0)
    setStarted(true)
  }, [])

  const endTour = useCallback(() => {
    setStarted(false)
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

  // Auto-start on the first signed-in visit, once the app shell it points at is on screen
  // (it used to start on the login page and cover the Sign in button).
  const firstTarget = steps[0]?.target
  useEffect(() => {
    if (!user) return
    try {
      if (localStorage.getItem(STORAGE_KEY)) return
    } catch {
      return
    }
    // Small delay so the DOM settles after initial render
    const t = setTimeout(() => {
      if (firstTarget && document.querySelector(firstTarget)) setStarted(true)
    }, 1200)
    return () => clearTimeout(t)
  }, [user, firstTarget])

  return (
    <TourContext.Provider
      value={{ isRunning, currentStep, totalSteps: steps.length, startTour, endTour }}
    >
      {children}
      {isRunning && steps[currentStep] && (
        <TourOverlay
          step={steps[currentStep]!}
          stepIndex={currentStep}
          totalSteps={steps.length}
          onNext={next}
          onPrev={prev}
          onSkip={endTour}
          text={text}
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
  /** The tour's words (English when not given). */
  text?: TourText
}

/** The tour's sheet: what this part of the screen is, and how far through the tour you are. */
export function TourPopover({
  step,
  stepIndex,
  totalSteps,
  onNext,
  onPrev,
  onSkip,
  nextRef,
  text = tourText('en'),
}: TourOverlayProps & { nextRef?: Ref<HTMLButtonElement> }) {
  const isLast = stepIndex === totalSteps - 1
  const pct = `${Math.round(((stepIndex + 1) / totalSteps) * 100)}%`
  return (
    <>
      <div className="flex items-center gap-2">
        <span className="text-xs text-subtle-foreground tabular">
          {text.stepOf(stepIndex + 1, totalSteps)}
        </span>
        <IconButton label={text.close} size="sm" className="-me-1.5 ms-auto" onClick={onSkip}>
          <X />
        </IconButton>
      </div>
      <div
        className="rz-progress"
        role="progressbar"
        aria-label={text.progress}
        aria-valuemin={1}
        aria-valuemax={totalSteps}
        aria-valuenow={stepIndex + 1}
      >
        <div className="rz-progress__bar" style={{ ['--_v' as string]: pct }} />
      </div>
      <div>
        <h2 id="rz-tour-title" className="m-0 text-[15px] font-semibold text-foreground">
          {step.title}
        </h2>
        <p
          id="rz-tour-desc"
          className="m-0 mt-1.5 text-[13px] leading-relaxed text-muted-foreground"
        >
          {step.description}
        </p>
      </div>
      <div className="flex items-center gap-2 pt-1">
        <Button variant="ghost" size="sm" className="-ms-2" onClick={onSkip}>
          {text.skip}
        </Button>
        <div className="ms-auto flex items-center gap-2">
          {stepIndex > 0 && (
            <Button size="sm" onClick={onPrev}>
              <ChevronLeft className="rtl:rotate-180" aria-hidden />
              {text.back}
            </Button>
          )}
          <Button ref={nextRef} variant="primary" size="sm" onClick={onNext}>
            {isLast ? text.finish : text.next}
            {!isLast && <ChevronRight className="rtl:rotate-180" aria-hidden />}
          </Button>
        </div>
      </div>
    </>
  )
}

function TourOverlay({
  step,
  stepIndex,
  totalSteps,
  onNext,
  onPrev,
  onSkip,
  text = tourText('en'),
}: TourOverlayProps) {
  const reduced = usePrefersReducedMotion()
  const [rect, setRect] = useState<Box | null>(() => measure(step.target))
  const [size, setSize] = useState({ width: 320, height: 200 })
  const popRef = useRef<HTMLDivElement>(null)
  const nextRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    const el = document.querySelector(step.target)
    setRect(measure(step.target))
    if (!el) return
    el.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'nearest' })
    // Measure again once the scroll has settled
    const t = setTimeout(() => setRect(measure(step.target)), 150)
    return () => clearTimeout(t)
  }, [step.target, reduced])

  // Follow the target when the window resizes or anything scrolls
  useEffect(() => {
    const handler = () => setRect(measure(step.target))
    window.addEventListener('resize', handler)
    window.addEventListener('scroll', handler, true)
    return () => {
      window.removeEventListener('resize', handler)
      window.removeEventListener('scroll', handler, true)
    }
  }, [step.target])

  // Place by the popover's real size (it grows with the description). Layout
  // size, not the bounding box: the entrance animation scales the box.
  useLayoutEffect(() => {
    const el = popRef.current
    if (!el) return
    const update = () => {
      const width = el.offsetWidth
      const height = el.offsetHeight
      setSize((s) =>
        Math.abs(s.width - width) > 0.5 || Math.abs(s.height - height) > 0.5
          ? { width, height }
          : s,
      )
    }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [stepIndex])

  // Keyboard: the primary action is under the person's hand, Escape leaves the tour
  useEffect(() => {
    nextRef.current?.focus({ preventScroll: true })
  }, [stepIndex])
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onSkip()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onSkip])

  const dir = document.documentElement.dir === 'rtl' ? 'rtl' : 'ltr'
  const place = placeTourPopover(
    rect,
    step.position,
    size,
    { width: window.innerWidth, height: window.innerHeight },
    dir,
  )

  return createPortal(
    <>
      {/* Click-catcher; it also dims the page when nothing is highlighted */}
      <div
        className="fixed inset-0 z-[9998] rz-fade"
        style={rect ? undefined : { background: 'var(--rz-overlay)' }}
        onClick={onSkip}
        aria-hidden
      />

      {/* Spotlight: a ring around the target; its shadow dims everything else */}
      {rect && (
        <div
          className="rz-spotlight z-[9999]"
          style={{
            left: rect.left - SPOT_PAD,
            top: rect.top - SPOT_PAD,
            width: rect.width + SPOT_PAD * 2,
            height: rect.height + SPOT_PAD * 2,
          }}
          aria-hidden
        />
      )}

      <div
        key={stepIndex}
        ref={popRef}
        role="dialog"
        lang={text.lang}
        dir={text.dir}
        aria-labelledby="rz-tour-title"
        aria-describedby="rz-tour-desc"
        className="rz-popover fixed z-[10000] grid w-[min(320px,calc(100vw-24px))] gap-3 p-4"
        style={{ left: place.left, top: place.top }}
        onClick={(e) => e.stopPropagation()}
      >
        <TourPopover
          step={step}
          stepIndex={stepIndex}
          totalSteps={totalSteps}
          onNext={onNext}
          onPrev={onPrev}
          onSkip={onSkip}
          nextRef={nextRef}
          text={text}
        />
      </div>
    </>,
    document.body,
  )
}
