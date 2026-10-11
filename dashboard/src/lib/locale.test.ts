import { describe, expect, it } from 'vitest'
import { baseLanguage, directionFor, resolveLanguage } from './locale'

describe('locale', () => {
  it('reads the base language of a locale tag', () => {
    expect(baseLanguage('he-IL')).toBe('he')
    expect(baseLanguage('pt_PT')).toBe('pt')
    expect(baseLanguage('')).toBe('en')
    expect(baseLanguage(undefined)).toBe('en')
  })

  it('turns right-to-left languages RTL', () => {
    expect(directionFor('he')).toBe('rtl')
    expect(directionFor('he-IL')).toBe('rtl')
    expect(directionFor('ar')).toBe('rtl')
    expect(directionFor('en')).toBe('ltr')
    expect(directionFor('pt')).toBe('ltr')
    expect(directionFor(null)).toBe('ltr')
  })

  it('follows the venture unless the person chose a language', () => {
    expect(resolveLanguage('auto', 'he')).toBe('he')
    expect(resolveLanguage('auto', '')).toBe('en')
    expect(resolveLanguage('en', 'he')).toBe('en')
    expect(resolveLanguage('he', 'en')).toBe('he')
  })
})
