/** The routing settings: what the form sends, and what it leaves alone. */
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/lib/api'
import {
  canonicalProvider,
  deadModels,
  formFromSettings,
  modelSuggestions,
  parseFallback,
  routingUpdate,
  saveRouting,
  type RoutingProvider,
  type RoutingSettings,
} from './llm-routing'

const SETTINGS: RoutingSettings = {
  primary: 'gemini',
  tiers: { fast: 'gemini/gemini-2.5-flash', standard: '', deep: 'anthropic/claude-opus-5-5' },
  fallback: ['gemini', 'claude'],
}

describe('provider names', () => {
  it('folds aliases to the registry name', () => {
    expect(canonicalProvider('anthropic')).toBe('claude')
    expect(canonicalProvider(' Google ')).toBe('gemini')
    expect(canonicalProvider('google_ai')).toBe('gemini')
    expect(canonicalProvider('openai')).toBe('openai')
    expect(canonicalProvider(null)).toBe('')
  })

  it('reads a fallback list: trimmed, lowercased, no empties', () => {
    expect(parseFallback(' Gemini, claude ,, OpenAI ')).toEqual(['gemini', 'claude', 'openai'])
    expect(parseFallback('')).toEqual([])
  })
})

describe('routingUpdate', () => {
  it('sends nothing when the form still matches the saved settings', () => {
    expect(routingUpdate(formFromSettings(SETTINGS), SETTINGS)).toBeNull()
  })

  it('treats an alias written in .env as the same primary', () => {
    const settings = { ...SETTINGS, primary: 'anthropic' }
    expect(routingUpdate(formFromSettings(settings), settings)).toBeNull()
  })

  it('sends only the fields that changed', () => {
    const form = formFromSettings(SETTINGS)
    form.primary = 'claude'
    form.tiers.standard = ' openai/gpt-4o '
    expect(routingUpdate(form, SETTINGS)).toEqual({
      primary: 'claude',
      tiers: { standard: 'openai/gpt-4o' },
    })
  })

  it('does not pin a tier the person left on its default', () => {
    const form = formFromSettings(SETTINGS)
    form.fallback = 'openai'
    const update = routingUpdate(form, SETTINGS)
    expect(update).toEqual({ fallback: ['openai'] })
    expect(update).not.toHaveProperty('tiers')
  })

  it('an emptied field unsets it', () => {
    const form = formFromSettings(SETTINGS)
    form.primary = ''
    form.tiers.fast = ''
    form.fallback = ''
    expect(routingUpdate(form, SETTINGS)).toEqual({
      primary: '',
      tiers: { fast: '' },
      fallback: [],
    })
  })

  it('works when the server sent no settings yet', () => {
    const form = formFromSettings(undefined)
    form.tiers.deep = 'ollama_chat/qwen3'
    expect(routingUpdate(form, undefined)).toEqual({ tiers: { deep: 'ollama_chat/qwen3' } })
  })
})

describe('saveRouting', () => {
  it('PUTs the update to /llm/routing and returns the rebuilt payload', async () => {
    const put = vi.fn(async () => ({ primary: 'claude' }))
    const result = await saveRouting({ primary: 'claude' }, put as never)
    expect(put).toHaveBeenCalledWith('/llm/routing', { primary: 'claude' })
    expect(result).toEqual({ primary: 'claude' })
  })

  it('lets the server error through, so the form can show its message', async () => {
    const put = vi.fn(async () => {
      throw new ApiError(400, 'tier model "bad model" is not a valid id')
    })
    await expect(saveRouting({ tiers: { fast: 'bad model' } }, put as never)).rejects.toThrow(
      'tier model "bad model" is not a valid id',
    )
  })
})

describe('models and dead models', () => {
  const providers: RoutingProvider[] = [
    {
      name: 'claude',
      available: true,
      models: [{ model_id: 'claude-opus-5-5' }, { model_id: 'claude-sonnet-5-5' }],
      model_errors: { 'claude-old': 'not found' },
    },
    { name: 'gemini', available: true, models: [{ model_id: 'claude-opus-5-5' }] },
    { name: 'openai', available: false, models: [{ model_id: 'openai/gpt-4o' }] },
  ]

  it('suggests each model of the available providers once', () => {
    expect(modelSuggestions(providers)).toEqual(['claude-opus-5-5', 'claude-sonnet-5-5'])
  })

  it('lists the models that stopped answering', () => {
    expect(deadModels(providers)).toEqual([{ provider: 'claude', model: 'claude-old' }])
  })
})
