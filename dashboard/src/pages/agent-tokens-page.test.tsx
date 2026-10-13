/**
 * STORY-37 in the dashboard: owners and admins list, create and revoke agent
 * tokens. The token is shown once, with a copy button and a plain warning;
 * the list never carries it; revoking asks first.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '@/hooks/use-auth'
import {
  EMPTY_FORM,
  INITIAL_TOKENS_STATE,
  type AgentToken,
  type TokensPageState,
} from '@/lib/agent-tokens'
import { agentTokensText } from '@/lib/agent-tokens-text'
import AgentTokensPage, {
  AgentTokensView,
  CONNECT_GUIDE_URL,
  type AgentTokensViewProps,
} from './agent-tokens-page'

const SECRET = 'rzag_3f9a0c1d2e4b_Zx9-secret-part-that-is-long-enough-123456'
const noop = () => {}

const ACTIVE: AgentToken = {
  id: '3f9a0c1d2e4b',
  name: 'claude-acme',
  principal: 'agent:3f9a0c1d2e4b',
  user: 'dana@acme.io',
  ventures: ['acme'],
  status: 'active',
  created_by: 'owner@realization.co.il',
  created_at: '2026-10-13T09:00:00+00:00',
  expires_at: '2027-01-11T09:00:00+00:00',
  last_used_at: null,
  revoked_at: null,
  revoked_by: null,
}

const REVOKED: AgentToken = {
  ...ACTIVE,
  id: '0a1b2c3d4e5f',
  name: 'old-cursor',
  status: 'revoked',
  revoked_at: '2026-10-12T09:00:00+00:00',
  revoked_by: 'owner@realization.co.il',
}

const VENTURES = [
  { key: 'acme', name: 'Acme Tower' },
  { key: 'globex', name: 'Globex Fund' },
]

function view(overrides: Partial<AgentTokensViewProps> = {}): string {
  const props: AgentTokensViewProps = {
    text: agentTokensText('en'),
    language: 'en',
    tokens: [ACTIVE, REVOKED],
    enabled: true,
    loading: false,
    error: null,
    ventures: VENTURES,
    form: { ...EMPTY_FORM, user: 'owner@realization.co.il' },
    onFormChange: noop,
    problems: [],
    createError: null,
    creating: false,
    onCreate: noop,
    state: INITIAL_TOKENS_STATE,
    onCopy: noop,
    onDismissCreated: noop,
    onAskRevoke: noop,
    onCancelRevoke: noop,
    onConfirmRevoke: noop,
    revokeBusy: false,
    onRefresh: noop,
    ...overrides,
  }
  return renderToStaticMarkup(
    <MemoryRouter>
      <AgentTokensView {...props} />
    </MemoryRouter>,
  )
}

function shown(state: Partial<TokensPageState>): TokensPageState {
  return {
    ...INITIAL_TOKENS_STATE,
    created: { token: SECRET, agent_token: ACTIVE },
    ...state,
  }
}

function occurrences(html: string, needle: string): number {
  return html.split(needle).length - 1
}

describe('AgentTokensView: the list', () => {
  it('lists every token with its user, ventures and state, never a secret', () => {
    const html = view()
    expect(html).toContain('data-token="3f9a0c1d2e4b"')
    expect(html).toContain('<bdi>claude-acme</bdi>')
    expect(html).toContain('<bdi>dana@acme.io</bdi>')
    expect(html).toContain('<bdi>acme</bdi>')
    expect(html).toContain('>Active<')
    expect(html).toContain('>Revoked<')
    expect(html).toContain('Not used yet')
    expect(html).not.toContain('rzag_')
  })

  it('only a token that still works can be revoked', () => {
    // Each row runs from its data-token to the next one (rows nest their venture list).
    const [, active, revoked] = view().split(/<li data-token=/)
    expect(active).toContain('"3f9a0c1d2e4b"')
    expect(active).toContain('>Revoke<')
    expect(revoked).toContain('"0a1b2c3d4e5f"')
    expect(revoked).not.toContain('>Revoke<')
  })

  it('links the connect guide', () => {
    const html = view()
    expect(html).toContain(`href="${CONNECT_GUIDE_URL}"`)
    expect(html).toContain('How to connect an agent')
    expect(html).toContain('rel="noopener noreferrer"')
  })

  it('no tokens yet', () => {
    const html = view({ tokens: [] })
    expect(html).toContain('No agent tokens yet')
  })

  it('the ventures to pick are the ones the person can see', () => {
    const html = view({ form: { ...EMPTY_FORM, ventures: ['globex'] } })
    expect(html).toMatch(/aria-pressed="false"[^>]*>.*?<bdi>Acme Tower<\/bdi>/s)
    expect(html).toMatch(/aria-pressed="true"[^>]*>.*?<bdi>Globex Fund<\/bdi>/s)
  })

  it('form problems are said next to their field', () => {
    const html = view({ problems: ['name', 'ventures'] })
    expect(html).toContain('aria-invalid="true"')
    expect(html).toContain('Use 1 to 64 letters')
    expect(html).toContain('Choose at least one venture.')
  })

  it('with the feature off, it says so and nothing can be created', () => {
    const html = view({ enabled: false })
    expect(html).toContain('data-flag="agent_tokens"')
    expect(html).toContain('Agent tokens are turned off')
    expect(html).toMatch(/<button type="submit"[^>]*disabled/)
  })
})

describe('AgentTokensView: create shows the token once', () => {
  it('the new token, a copy button, and a plain "you won’t see it again"', () => {
    const html = view({ state: shown({}) })
    expect(occurrences(html, SECRET)).toBe(1) // in the read-only field, nowhere else
    expect(html).toMatch(/<input[^>]*readOnly=""[^>]*value="rzag_/i)
    expect(html).toContain('Copy the token now')
    expect(html).toContain('You won’t see it again')
    expect(html).toContain('Token for claude-acme')
    expect(html).toMatch(/<button[^>]*>.*?Copy<\/button>/s)
    expect(html).toContain('I’ve copied it')
    expect(html).toContain(
      '<code dir="ltr" class="font-mono">Authorization: Bearer &lt;token&gt;</code>',
    )
  })

  it('after copying, the button says so', () => {
    const html = view({ state: shown({ copy: 'copied' }) })
    expect(html).toMatch(/<button[^>]*>.*?Copied<\/button>/s)
  })

  it('a failed copy tells the person to copy by hand', () => {
    const html = view({ state: shown({ copy: 'failed' }) })
    expect(html).toContain('role="alert"')
    expect(html).toContain('Select the token and copy it by hand')
  })

  it('once dismissed, the token is gone from the page', () => {
    expect(view({ state: INITIAL_TOKENS_STATE })).not.toContain(SECRET)
  })

  it('a refused create says why', () => {
    const html = view({ createError: "Couldn’t create the token: No user 'x@y.io' in users.yaml" })
    expect(html).toContain('No user &#x27;x@y.io&#x27; in users.yaml')
  })
})

describe('AgentTokensView: revoke asks first', () => {
  it('the confirm names the token and what revoking does', () => {
    const html = view({ state: { ...INITIAL_TOKENS_STATE, revoking: ACTIVE } })
    expect(html).toContain('Revoke claude-acme?')
    expect(html).toContain('The agent stops working at once')
    expect(html).toContain('withdrawn')
    expect(html).toContain('Revoke token')
    expect(html).toContain('>Cancel<')
  })
})

describe('AgentTokensPage gating', () => {
  it('someone who can’t manage tokens is told why, and nothing is fetched or shown', () => {
    // Outside a session (no user), as for any person without the role.
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <AuthProvider>
          <AgentTokensPage />
        </AuthProvider>
      </MemoryRouter>,
    )
    expect(html).toContain('data-gate="agent-tokens"')
    expect(html).toContain('Only an owner or admin with access to every venture')
    expect(html).not.toContain('Create token')
  })
})

describe('AgentTokensView in Hebrew', () => {
  it('words in Hebrew; names, emails and the token stay isolated', () => {
    const html = view({ text: agentTokensText('he'), language: 'he', state: shown({}) })
    expect(html).toContain('טוקנים לסוכנים')
    expect(html).toContain('העתיקו את הטוקן עכשיו')
    expect(html).toContain('לא תוכלו לראות אותו שוב')
    expect(html).toContain('>שלילה<')
    expect(html).toContain('<bdi>dana@acme.io</bdi>')
    expect(html).toMatch(/<input[^>]*dir="ltr"[^>]*value="rzag_/)
  })
})
