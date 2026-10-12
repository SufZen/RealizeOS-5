import { describe, expect, it } from 'vitest'
import { isLocked, resolveSelection } from './use-venture'

const VENTURES = [
  { key: 'acme', name: 'Acme Tower' },
  { key: 'globex', name: 'Globex Fund' },
]

describe('venture selection', () => {
  it('keeps a stored choice that is still available', () => {
    expect(resolveSelection(VENTURES, 'globex')).toBe('globex')
  })

  it('falls back to the first venture when the stored one is gone or not allowed', () => {
    expect(resolveSelection(VENTURES, 'initech')).toBe('acme')
    expect(resolveSelection(VENTURES, '')).toBe('acme')
    expect(resolveSelection([], 'acme')).toBe('')
  })

  it('locks the view only for users limited to exactly one venture', () => {
    expect(isLocked(['acme'])).toBe(true)
    expect(isLocked(['acme', 'globex'])).toBe(false)
    expect(isLocked(null)).toBe(false)
    expect(isLocked(undefined)).toBe(false)
  })
})
