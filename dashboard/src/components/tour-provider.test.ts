/**
 * Guided tour placement: the popover sits beside what it explains, mirrors in
 * RTL (the sidebar is on the right there), and never leaves the window.
 */
import { describe, expect, it } from 'vitest'
import { DEFAULT_TOUR_STEPS, placeTourPopover } from './tour-provider'

const VIEW = { width: 1440, height: 900 }
const POP = { width: 320, height: 180 }
/** A sidebar row in LTR: 248px sidebar, row inset by 12px. */
const NAV_LTR = { left: 12, top: 100, width: 224, height: 32 }
/** The same row in RTL: the sidebar is on the right. */
const NAV_RTL = { left: 1440 - 12 - 224, top: 100, width: 224, height: 32 }

describe('placeTourPopover', () => {
  it('sits beside the item, vertically centred on it', () => {
    expect(placeTourPopover(NAV_LTR, 'right', POP, VIEW)).toEqual({
      left: 12 + 224 + 16,
      top: 100 + 16 - 90,
    })
  })

  it('mirrors in RTL, so the popover opens away from the sidebar', () => {
    const p = placeTourPopover(NAV_RTL, 'right', POP, VIEW, 'rtl')
    expect(p.left).toBe(NAV_RTL.left - 16 - 320)
    expect(p.left + POP.width).toBeLessThanOrEqual(NAV_RTL.left)
  })

  it('takes the other side when the preferred one has no room', () => {
    // LTR "right" for an item at the right edge: no room, so it opens to the left
    const p = placeTourPopover(NAV_RTL, 'right', POP, VIEW, 'ltr')
    expect(p.left).toBe(NAV_RTL.left - 16 - 320)
  })

  it('stays inside the window', () => {
    const low = { left: 12, top: 870, width: 224, height: 24 }
    const p = placeTourPopover(low, 'right', POP, VIEW)
    expect(p.top).toBe(900 - 180 - 12)
    const phone = placeTourPopover(NAV_LTR, 'right', POP, { width: 390, height: 844 })
    expect(phone.left).toBeGreaterThanOrEqual(12)
    expect(phone.left + POP.width).toBeLessThanOrEqual(390 - 12)
  })

  it('centres when the target is missing or hidden (folded sidebar on a phone)', () => {
    const centred = { left: (1440 - 320) / 2, top: (900 - 180) / 2 }
    expect(placeTourPopover(null, 'right', POP, VIEW)).toEqual(centred)
    expect(placeTourPopover({ left: 0, top: 0, width: 0, height: 0 }, 'right', POP, VIEW)).toEqual(
      centred,
    )
  })
})

describe('DEFAULT_TOUR_STEPS', () => {
  it('speaks plainly: no emoji in titles or descriptions', () => {
    for (const s of DEFAULT_TOUR_STEPS) {
      expect(`${s.title} ${s.description}`).not.toMatch(/\p{Extended_Pictographic}/u)
    }
  })
})
