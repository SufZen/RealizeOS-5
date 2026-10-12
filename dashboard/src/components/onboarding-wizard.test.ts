/** QA 5.14 D-1: the wizard is for a server with no AI provider, not for every new browser. */
import { describe, expect, it } from 'vitest'
import { serverHasAiProvider } from './onboarding-wizard'

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
