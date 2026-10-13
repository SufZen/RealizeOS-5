/**
 * Review D8: the agent-tokens "not allowed" page linked its Settings crumb
 * for everyone, so a person limited to some ventures was sent to a Settings
 * page that refuses them. The link is there only for someone who may open it.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { agentTokensText } from '@/lib/agent-tokens-text'
import { canOpenPage } from '@/lib/permissions'
import { NotAllowed } from './agent-tokens-page'

function page(settingsLink: boolean, language = 'en'): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <NotAllowed text={agentTokensText(language)} settingsLink={settingsLink} />
    </MemoryRouter>,
  )
}

describe('NotAllowed', () => {
  it('an operator with every venture may open Settings: the crumb links there', () => {
    const operator = { role: 'operator', ventures: null }
    expect(canOpenPage(operator, '/settings')).toBe(true)
    const html = page(true)
    expect(html).toContain('href="/settings"')
    expect(html).toContain('data-gate="agent-tokens"')
  })

  it('a venture-limited person can’t: no link to a page that would refuse them', () => {
    const limited = { role: 'admin', ventures: ['acme'] }
    expect(canOpenPage(limited, '/settings')).toBe(false)
    const html = page(false, 'he')
    expect(html).not.toContain('href="/settings"')
    expect(html).not.toContain('aria-label="Breadcrumb"')
    expect(html).toContain('data-gate="agent-tokens"')
  })
})
