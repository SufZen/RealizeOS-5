/** The routing form: prefilled from the saved settings, LTR model ids, EN and HE. */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { RoutingData } from '@/lib/llm-routing'
import { llmSettingsText } from '@/lib/llm-settings-text'
import { LLMRoutingForm } from '@/pages/settings/settings-advanced'

const DATA: RoutingData = {
  routing_rules: {},
  tiers: {
    fast: { provider: 'gemini', model: 'gemini/gemini-2.5-flash', source: 'env' },
    standard: { provider: 'gemini', model: 'gemini/gemini-2.5-pro', source: 'default' },
    deep: { provider: 'claude', model: 'claude-opus-5-5', source: 'env' },
  },
  providers: [
    { name: 'claude', available: true, models: [{ model_id: 'claude-opus-5-5' }] },
    { name: 'gemini', available: true, models: [{ model_id: 'gemini/gemini-2.5-pro' }] },
    { name: 'openai', available: false, models: [] },
  ],
  primary: 'gemini',
  fallback: ['gemini', 'claude'],
  settings: {
    primary: 'gemini',
    tiers: { fast: 'gemini/gemini-2.5-flash', standard: '', deep: 'claude-opus-5-5' },
    fallback: ['gemini', 'claude'],
  },
}

function render(language: string, data: RoutingData = DATA): string {
  return renderToStaticMarkup(
    <LLMRoutingForm data={data} text={llmSettingsText(language)} onSave={async () => {}} />,
  )
}

describe('LLMRoutingForm', () => {
  const html = render('en')

  it('prefills the tiers from the saved settings and shows the default for an unset one', () => {
    expect(html).toContain('value="gemini/gemini-2.5-flash"')
    expect(html).toContain('value="claude-opus-5-5"')
    expect(html).toContain('placeholder="gemini/gemini-2.5-pro"')
  })

  it('selects the saved primary among the providers that answer', () => {
    expect(html).toMatch(/<option value="gemini" selected="">gemini<\/option>/)
    expect(html).toContain('<option value="claude">claude</option>')
    expect(html).not.toContain('value="openai"')
  })

  it('keeps a chosen primary visible when it cannot answer now', () => {
    const down = { ...DATA, settings: { ...DATA.settings, primary: 'openai' } }
    expect(render('en', down)).toContain('openai (not available)')
  })

  it('prefills the fallback order and offers model suggestions', () => {
    expect(html).toContain('value="gemini, claude"')
    expect(html).toContain('<datalist')
    expect(html).toContain('<option value="claude-opus-5-5"')
  })

  it('model and fallback inputs read their own direction', () => {
    const inputs = [...html.matchAll(/<input [^>]*>/g)].map((m) => m[0])
    expect(inputs).toHaveLength(4)
    for (const input of inputs) expect(input).toContain('dir="auto"')
  })

  it('nothing to save until something changes', () => {
    expect(html).toMatch(/<button type="submit" disabled=""[^>]*>Save routing<\/button>/)
    expect(html).toContain('No changes')
  })

  it('uses logical spacing only (no left/right utilities)', () => {
    expect(html).not.toMatch(/class="[^"]*\b(ml|mr|pl|pr|text-left|text-right)-/)
  })

  it('speaks Hebrew, with no English UI words left', () => {
    const he = render('he')
    expect(he).toContain('ספק ראשי')
    expect(he).toContain('מודל לכל רמה')
    expect(he).toContain('שמירת הניתוב')
    expect(he).not.toContain('Primary provider')
    expect(he).not.toContain('Save routing')
  })
})
