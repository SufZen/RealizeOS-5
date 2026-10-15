/**
 * Setup: any provider can be the primary one. No provider is "recommended",
 * LiteLLM can be connected, and once a provider is connected the connect step
 * offers the primary choice (saved through PUT /llm/routing).
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { onboardingText } from '@/lib/onboarding-text'
import {
  ConnectStep,
  LLM_PROVIDERS,
  PrimaryProviderChoice,
  ProviderCard,
  serverHasAiProvider,
} from './onboarding-wizard'

const save = async () => {}

function connectStep(connected: string[], language = 'en', withChoice = true): string {
  return renderToStaticMarkup(
    <ConnectStep
      connected={new Set(connected)}
      onSave={save}
      primary=""
      onPrimary={withChoice ? save : undefined}
      text={onboardingText(language)}
    />,
  )
}

describe('providers', () => {
  it('none is recommended over the others', () => {
    expect(LLM_PROVIDERS.every((p) => !('recommended' in p))).toBe(true)
    for (const language of ['en', 'he']) {
      expect(connectStep([], language)).not.toMatch(/Recommended|מומלץ/)
    }
  })

  it('LiteLLM is offered, with a model field and an optional gateway URL', () => {
    const litellm = LLM_PROVIDERS.find((p) => p.id === 'litellm')
    expect(litellm).toMatchObject({ isModel: true, baseUrlId: 'litellm_api_base' })
    const html = renderToStaticMarkup(
      <ul>
        <ProviderCard
          provider={litellm!}
          configured={false}
          onSave={save}
          text={onboardingText('en')}
        />
      </ul>,
    )
    expect(html).toContain('Model')
    expect(html).toContain('API base URL (optional)')
    // The model id is a plain, visible text field that reads its own direction.
    expect(html).toMatch(/<input[^>]*type="text"[^>]*dir="auto"/)
    expect(html).not.toContain('type="password"')
  })

  it('LiteLLM has a description and help in both languages', () => {
    for (const language of ['en', 'he']) {
      const words = onboardingText(language).providers.litellm
      expect(words.description).toBeTruthy()
      expect(words.help).toContain('mistral/mistral-large-latest')
    }
    expect(onboardingText('he').providers.litellm.description).toMatch(/[א-ת]/)
  })
})

describe('primary provider choice', () => {
  it('is not offered until a provider is connected', () => {
    expect(connectStep([])).not.toContain('Primary provider')
  })

  it('lists automatic plus each connected provider, by routing name', () => {
    const html = connectStep(['anthropic', 'google_ai', 'litellm'])
    expect(html).toContain('Primary provider')
    expect(html).toMatch(/<option value=""[^>]*>Automatic \(first available\)<\/option>/)
    expect(html).toContain('<option value="claude">Claude (Anthropic)</option>')
    expect(html).toContain('<option value="gemini">Gemini (Google)</option>')
    expect(html).toContain('<option value="litellm">LiteLLM (any other)</option>')
    expect(html).not.toContain('value="openai"')
    expect(html).not.toContain('value="ollama"')
  })

  it('speaks Hebrew', () => {
    const html = connectStep(['openai'], 'he')
    expect(html).toContain('ספק ראשי')
    expect(html).toContain('אוטומטי (הראשון הזמין)')
    expect(html).not.toContain('Primary provider')
  })

  it('shows the chosen provider as selected', () => {
    const html = renderToStaticMarkup(
      <PrimaryProviderChoice
        connected={LLM_PROVIDERS.filter((p) => p.id === 'openai' || p.id === 'ollama')}
        value="ollama"
        onChoose={save}
        text={onboardingText('en')}
      />,
    )
    expect(html).toMatch(/<option value="ollama" selected="">/)
  })
})

describe('serverHasAiProvider', () => {
  it('routing settings in the llm category are not a provider', () => {
    expect(
      serverHasAiProvider([
        { id: 'llm_primary', category: 'llm', configured: true },
        { id: 'litellm_api_base', category: 'llm', configured: true },
        { id: 'anthropic', category: 'llm', configured: false },
      ]),
    ).toBe(false)
    expect(
      serverHasAiProvider([
        { id: 'llm_primary', category: 'llm', configured: true },
        { id: 'litellm', category: 'llm', configured: true },
      ]),
    ).toBe(true)
  })
})

describe('primary choice shows what is saved', () => {
  it('keeps a saved primary selected when its provider is not connected here', () => {
    const html = renderToStaticMarkup(
      <PrimaryProviderChoice
        connected={LLM_PROVIDERS.filter((p) => p.id === 'anthropic')}
        value="ollama"
        onChoose={save}
        text={onboardingText('en')}
      />,
    )
    expect(html).toContain('<option value="ollama" selected="">ollama</option>')
  })

  it('selects the saved connected provider', () => {
    const html = renderToStaticMarkup(
      <ConnectStep
        connected={new Set(['anthropic', 'google_ai'])}
        onSave={save}
        primary="gemini"
        onPrimary={save}
        text={onboardingText('en')}
      />,
    )
    expect(html).toContain('<option value="gemini" selected="">Gemini (Google)</option>')
  })
})
