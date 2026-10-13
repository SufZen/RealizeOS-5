/**
 * Review D9: the guided tour spoke English only and inherited right-to-left
 * in Hebrew, so its punctuation flipped. It now speaks the person's language
 * through the locale mechanism, with the same steps, targets and sides.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { tourText } from '@/lib/tour-text'
import { DEFAULT_TOUR_STEPS, TourPopover, tourSteps } from './tour-provider'

const noop = () => {}
const HEBREW = /[֐-׿]/

describe('tourSteps', () => {
  it('Hebrew keeps every step’s target and side, in Hebrew words', () => {
    const he = tourSteps('he-IL')
    expect(he).toHaveLength(DEFAULT_TOUR_STEPS.length)
    he.forEach((step, i) => {
      expect(step.target).toBe(DEFAULT_TOUR_STEPS[i]!.target)
      expect(step.position).toBe(DEFAULT_TOUR_STEPS[i]!.position)
      expect(step.title).toMatch(HEBREW)
      expect(step.description).toMatch(HEBREW)
    })
  })

  it('English stays as it was; any other language reads English', () => {
    expect(DEFAULT_TOUR_STEPS[0]!.title).toBe('Welcome to RealizeOS')
    expect(tourSteps('fr')).toEqual(DEFAULT_TOUR_STEPS)
  })

  it('no emoji in either language', () => {
    for (const s of tourSteps('he')) {
      expect(`${s.title} ${s.description}`).not.toMatch(/\p{Extended_Pictographic}/u)
    }
  })
})

describe('TourPopover', () => {
  const he = tourText('he')
  const step = tourSteps('he')[1]!

  it('controls and progress in Hebrew', () => {
    const html = renderToStaticMarkup(
      <TourPopover
        step={step}
        stepIndex={1}
        totalSteps={16}
        onNext={noop}
        onPrev={noop}
        onSkip={noop}
        text={he}
      />,
    )
    expect(html).toContain('שלב 2 מתוך 16')
    expect(html).toContain('aria-label="סגירת הסיור"')
    expect(html).toContain('aria-label="התקדמות הסיור"')
    expect(html).toContain('דילוג על הסיור')
    expect(html).toContain('הקודם')
    expect(html).toContain('הבא')
    expect(html).toContain(step.title)
    expect(html).not.toMatch(/Step \d|Skip tour|>Next<|>Back</)
  })

  it('the last step finishes', () => {
    const html = renderToStaticMarkup(
      <TourPopover
        step={step}
        stepIndex={15}
        totalSteps={16}
        onNext={noop}
        onPrev={noop}
        onSkip={noop}
        text={he}
      />,
    )
    expect(html).toContain('סיום')
  })

  it('English by default', () => {
    const html = renderToStaticMarkup(
      <TourPopover
        step={DEFAULT_TOUR_STEPS[0]!}
        stepIndex={0}
        totalSteps={16}
        onNext={noop}
        onPrev={noop}
        onSkip={noop}
      />,
    )
    expect(html).toContain('Step 1 of 16')
    expect(html).toContain('Skip tour')
  })

  it('the tour words carry their direction for the popover', () => {
    expect(tourText('he')).toMatchObject({ lang: 'he', dir: 'rtl' })
    expect(tourText('en')).toMatchObject({ lang: 'en', dir: 'ltr' })
  })
})
