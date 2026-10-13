/** QA 5.14 D-1: the wizard is for a server with no AI provider, not for every new browser. */
import { describe, expect, it } from 'vitest'
import { ApiError } from '@/lib/api'
import { saveErrorText, serverHasAiProvider } from './onboarding-wizard'

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
