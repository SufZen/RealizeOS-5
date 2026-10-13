/**
 * Review D3 and D4 on first-run setup:
 * - D3: only someone who may connect a provider gets the wizard (saving a key
 *   needs system:manage and every venture); a viewer, user or operator on a
 *   server without a provider gets a notice they can close, not a wizard
 *   whose Continue never enables.
 * - D4: in Hebrew, the show/hide-key button sits at the end of the key field,
 *   where its padding is, not over the key's first characters.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { onboardingText } from '@/lib/onboarding-text'
import {
  LLM_PROVIDERS,
  ProviderCard,
  ProviderNeededNotice,
  onboardingPrompt,
} from './onboarding-wizard'

const OWNER = { role: 'owner', ventures: null }
const ADMIN = { role: 'admin', ventures: null }
const noop = () => {}

describe('onboardingPrompt (D3)', () => {
  it('an owner or admin on a server without a provider gets the wizard', () => {
    expect(onboardingPrompt(OWNER, 'needed')).toBe('wizard')
    expect(onboardingPrompt(ADMIN, 'needed')).toBe('wizard')
    // A failed check still offers it, as before.
    expect(onboardingPrompt(OWNER, 'unreachable')).toBe('wizard')
  })

  it('viewers, users and operators get the notice instead', () => {
    for (const role of ['viewer', 'user', 'operator']) {
      expect(onboardingPrompt({ role, ventures: null }, 'needed')).toBe('notice')
      // Nothing when the check failed: we don't know there's no provider.
      expect(onboardingPrompt({ role, ventures: null }, 'unreachable')).toBeNull()
    }
  })

  it('a custom role without system:manage gets the notice', () => {
    const custom = { role: 'approver', ventures: null, permissions: ['pipeline:approve'] }
    expect(onboardingPrompt(custom, 'needed')).toBe('notice')
  })

  it('nothing once a provider is connected, before the server answers, or when signed out', () => {
    expect(onboardingPrompt(OWNER, 'done')).toBeNull()
    expect(onboardingPrompt({ role: 'viewer', ventures: null }, 'done')).toBeNull()
    expect(onboardingPrompt(OWNER, 'unknown')).toBeNull()
    expect(onboardingPrompt(null, 'needed')).toBeNull()
  })

  it('a person limited to some ventures gets neither (they can’t read setup)', () => {
    expect(onboardingPrompt({ role: 'owner', ventures: ['acme'] }, 'needed')).toBeNull()
    expect(onboardingPrompt({ role: 'viewer', ventures: ['acme'] }, 'needed')).toBeNull()
  })
})

describe('ProviderNeededNotice (D3)', () => {
  it('says who has to connect a provider, and can be closed', () => {
    const html = renderToStaticMarkup(
      <ProviderNeededNotice onDismiss={noop} text={onboardingText('en')} />,
    )
    expect(html).toContain('data-notice="provider-needed"')
    expect(html).toContain('An owner or admin needs to connect an AI provider')
    expect(html).toContain('aria-label="Dismiss"')
  })

  it('in Hebrew', () => {
    const html = renderToStaticMarkup(
      <ProviderNeededNotice onDismiss={noop} text={onboardingText('he')} />,
    )
    expect(html).toContain('בעלים או מנהל צריכים לחבר ספק AI')
    expect(html).toContain('aria-label="סגירה"')
  })
})

describe('ProviderCard key field (D4)', () => {
  const anthropic = LLM_PROVIDERS.find((p) => p.id === 'anthropic')!

  it('in Hebrew, the field and its show/hide button share one left-to-right box', () => {
    const html = renderToStaticMarkup(
      <ProviderCard
        provider={anthropic}
        configured={false}
        onSave={async () => {}}
        text={onboardingText('he')}
      />,
    )
    // The wrapper sets the direction, so `pe-10` (the input's room for the
    // button) and `end-[3px]` (the button) are on the same side.
    expect(html).toMatch(
      /<div dir="ltr" class="relative min-w-0 flex-1"><input[^>]*class="[^"]*pe-10/,
    )
    expect(html).toMatch(/aria-label="הצגת המפתח"[^>]*class="[^"]*end-\[3px\]/)
  })
})
