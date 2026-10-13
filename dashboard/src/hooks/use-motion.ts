import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'

const REDUCED_QUERY = '(prefers-reduced-motion: reduce)'

/** True when the person asked the OS for less motion. Updates live. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(REDUCED_QUERY).matches,
  )
  useEffect(() => {
    const mql = window.matchMedia(REDUCED_QUERY)
    const onChange = () => setReduced(mql.matches)
    mql.addEventListener('change', onChange)
    return () => mql.removeEventListener('change', onChange)
  }, [])
  return reduced
}

/**
 * Animate a number from its previous value to `value` with an ease-out curve.
 * For figures that change in front of the person (a total that updates after
 * an approval). Jumps straight to the value on reduced motion.
 */
export function useCountUp(value: number, durationMs = 700): number {
  const reduced = usePrefersReducedMotion()
  const [shown, setShown] = useState(reduced ? value : 0)
  const from = useRef(reduced ? value : 0)

  useEffect(() => {
    if (reduced) {
      from.current = value
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setShown(value)
      return
    }
    const start = performance.now()
    const a = from.current
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - Math.pow(1 - t, 4)
      setShown(a + (value - a) * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
      else from.current = value
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      from.current = value
    }
  }, [value, durationMs, reduced])

  return shown
}

/**
 * Measure the selected child of a container and expose its offset and width
 * as CSS variables (--_x, --_w) on the indicator element. Drives the gliding
 * ink under tabs and the thumb of segmented controls. Works in RTL because it
 * measures real positions rather than indexes.
 */
export function useIndicator<T extends HTMLElement>(
  containerRef: RefObject<T | null>,
  selector: string,
): RefObject<HTMLSpanElement | null> {
  const indicatorRef = useRef<HTMLSpanElement | null>(null)

  // Re-measure after every render: the selection, the text or the writing
  // direction may have changed, and a direction flip resizes nothing.
  useLayoutEffect(() => {
    const container = containerRef.current
    const indicator = indicatorRef.current
    if (!container || !indicator) return
    const place = () => {
      const active = container.querySelector<HTMLElement>(selector)
      if (!active) {
        indicator.style.setProperty('--_w', '0px')
        return
      }
      const c = container.getBoundingClientRect()
      const a = active.getBoundingClientRect()
      // The first placement jumps; only later changes glide (motion answers an action)
      const first = !indicator.dataset.placed
      if (first) indicator.style.transition = 'none'
      indicator.style.setProperty('--_x', `${a.left - c.left}px`)
      indicator.style.setProperty('--_w', `${a.width}px`)
      if (first) {
        indicator.dataset.placed = 'true'
        requestAnimationFrame(() => indicator.style.removeProperty('transition'))
      }
    }
    place()
    // Fonts arriving late change widths without a render
    document.fonts?.ready.then(place).catch(() => undefined)
    const ro = new ResizeObserver(place)
    ro.observe(container)
    const dirWatch = new MutationObserver(place)
    dirWatch.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['dir', 'lang'],
    })
    return () => {
      ro.disconnect()
      dirWatch.disconnect()
    }
  })

  return indicatorRef
}
