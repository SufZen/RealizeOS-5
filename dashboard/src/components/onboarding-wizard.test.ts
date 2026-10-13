/** QA 5.14 D-1: the wizard is for a server with no AI provider, not for every new browser. */
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { onboardingText } from '@/lib/onboarding-text'
import { LLM_PROVIDERS, saveErrorText, serverHasAiProvider } from './onboarding-wizard'

describe('serverHasAiProvider', () => {
  it('is true once any AI provider is configured', () => {
    expect(
      serverHasAiProvider([
        { category: 'llm', configured: false },
        { category: 'llm', configured: true },
      ]),
    ).toBe(true)
  })

  it('ignores tools and integrations', () => {
    expect(
      serverHasAiProvider([
        { category: 'tool', configured: true },
        { category: 'integration', configured: true },
        { category: 'llm', configured: false },
      ]),
    ).toBe(false)
  })

  it('is false for an empty list', () => {
    expect(serverHasAiProvider([])).toBe(false)
  })
})

/** A key that fails to save says so, instead of failing silently. */
describe('saveErrorText', () => {
  it("carries the server's reason", () => {
    expect(saveErrorText(new ApiError(400, 'Invalid API key format'))).toBe(
      'Couldn’t connect: Invalid API key format',
    )
  })

  it('falls back to a plain instruction when there is no reason', () => {
    expect(saveErrorText(new Error('  '))).toBe('Couldn’t connect. Check the value and try again.')
    expect(saveErrorText('offline')).toBe('Couldn’t connect. Check the value and try again.')
  })
})

/** The wizard speaks the person's language (Hebrew and English carry every string). */
describe('onboarding words', () => {
  it('a save error in Hebrew', () => {
    const he = onboardingText('he')
    expect(saveErrorText(new ApiError(400, 'Invalid API key format'), he)).toBe(
      'החיבור נכשל: Invalid API key format',
    )
    expect(saveErrorText(new Error(''), he)).toBe('החיבור נכשל. כדאי לבדוק את הערך ולנסות שוב.')
  })

  it('both languages describe every provider, and pick their direction', () => {
    for (const language of ['en', 'he', 'he-IL']) {
      const text = onboardingText(language)
      for (const p of LLM_PROVIDERS) {
        expect(text.providers[p.id].description).toBeTruthy()
        expect(text.providers[p.id].help).toBeTruthy()
      }
    }
    expect(onboardingText('he-IL').dir).toBe('rtl')
    expect(onboardingText('fr').dir).toBe('ltr')
    expect(onboardingText('he').switchTarget).toBe('en')
    expect(onboardingText('en').switchTarget).toBe('he')
  })

  it('Hebrew counts read naturally', () => {
    const he = onboardingText('he')
    expect(he.providerCount(1)).toBe('ספק אחד')
    expect(he.providerCount(3)).toBe('3 ספקים')
    expect(onboardingText('en').providerCount(1)).toBe('1 provider')
    expect(onboardingText('en').providerCount(2)).toBe('2 providers')
  })
})
