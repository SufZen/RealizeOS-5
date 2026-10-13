/**
 * Review D10: sentences that explain a gate or a failure were English only.
 * Each now comes in Hebrew through the locale mechanism; English is unchanged.
 */
import { describe, expect, it } from 'vitest'
import { agentChangeFailed } from './agent-text'
import { kbEmptyHint } from './kb-text'
import { agentControlsGate, editKnowledgeGate, setupGate, ventureGates } from './permissions'
import { shellText } from './shell-text'

const HEBREW = /[֐-׿]/
const VIEWER = { role: 'viewer', ventures: null }

describe('permission gates in Hebrew', () => {
  it('ventures: every notice', () => {
    expect(ventureGates(VIEWER, true, 'he').notice).toBe(
      'התפקיד שלך (viewer) לא מאפשר ליצור או למחוק מיזמים. אפשר לפנות לבעלים או למנהל.',
    )
    expect(ventureGates({ role: 'user', permissions: ['system:delete'] }, true, 'he').notice).toBe(
      'התפקיד שלך (user) לא מאפשר ליצור מיזמים. אפשר לפנות לבעלים או למנהל.',
    )
    expect(ventureGates({ role: 'admin', ventures: ['acme'] }, true, 'he-IL').notice).toContain(
      'הגישה שלך מוגבלת לחלק מהמיזמים',
    )
    expect(
      ventureGates({ role: 'x', ventures: null, permissions: ['system:manage'] }, true, 'he')
        .notice,
    ).toBe('התפקיד שלך (x) לא מאפשר למחוק מיזמים. אפשר לפנות לבעלים או למנהל.')
  })

  it('knowledge base, setup and agent controls', () => {
    expect(editKnowledgeGate(VIEWER, 'he')).toContain('צפייה בלבד: התפקיד שלך (viewer)')
    expect(setupGate(VIEWER, 'he')).toBe(
      'כדי לחבר ספקים וליצור את המיזם הראשון, יש לפנות לבעלים או למנהל.',
    )
    expect(agentControlsGate(VIEWER, 'he')).toMatch(HEBREW)
    expect(agentControlsGate(VIEWER, 'he')).toContain('(viewer)')
  })

  it('nothing to explain when the role may: null in any language', () => {
    const owner = { role: 'owner', ventures: null }
    expect(ventureGates(owner, true, 'he').notice).toBeNull()
    expect(editKnowledgeGate(owner, 'he')).toBeNull()
    expect(setupGate(owner, 'he')).toBeNull()
    expect(agentControlsGate(owner, 'he')).toBeNull()
  })

  it('English stays the default and is unchanged', () => {
    expect(setupGate(VIEWER)).toBe(
      'Ask an owner or admin to connect providers and create the first venture.',
    )
    expect(setupGate(VIEWER, 'fr')).toBe(setupGate(VIEWER))
    expect(editKnowledgeGate(VIEWER, 'en')).toBe(
      'View only: your role (viewer) can read the knowledge base but not change it.',
    )
  })
})

describe('other sentences', () => {
  it('the knowledge base hint', () => {
    expect(kbEmptyHint(true, 'he')).toBe('בחרו קובץ לצפייה, או חפשו בבסיס הידע')
    expect(kbEmptyHint(false, 'he')).toContain('לעריכה')
    expect(kbEmptyHint(true, 'en')).toBe('Select a file to view, or search the knowledge base')
  })

  it('the agent pause/resume toast', () => {
    expect(agentChangeFailed('pause', 'he')).toBe('לא ניתן היה להשהות את הסוכן')
    expect(agentChangeFailed('resume', 'he')).toBe('לא ניתן היה לחדש את הסוכן')
    expect(agentChangeFailed('pause', 'en')).toBe('Couldn’t pause the agent')
  })

  it('the nav badge’s accessible name', () => {
    expect(shellText('he').heldForYou(1)).toBe('פריט אחד ממתין לך')
    expect(shellText('he').heldForYou(3)).toBe('3 פריטים ממתינים לך')
    expect(shellText('en').heldForYou(3)).toBe('3 held for you')
  })
})
