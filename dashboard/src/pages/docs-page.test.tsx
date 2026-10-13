/**
 * Review D13: the Docs page linked a "Full Standalone Guide" at
 * `/docs/user-guide.html`, which the server doesn't ship (a 404). It now
 * links the documentation index on GitHub.
 */
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import DocsPage, { FULL_DOCS_URL } from './docs-page'

describe('DocsPage', () => {
  it('links the docs index on GitHub, not a guide the server doesn’t ship', () => {
    expect(FULL_DOCS_URL).toBe('https://github.com/SufZen/RealizeOS-5/blob/main/docs/README.md')
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <DocsPage />
      </MemoryRouter>,
    )
    expect(html).toContain(`href="${FULL_DOCS_URL}"`)
    expect(html).not.toContain('user-guide.html')
    expect(html).toContain('rel="noopener noreferrer"')
  })
})
