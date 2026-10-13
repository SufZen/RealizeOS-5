/**
 * Agent tokens in the dashboard (STORY-37): list, create, revoke.
 *
 * Mirrors `realize_api/routes/agent_tokens.py`. The token itself comes back
 * once, in the create response: it is kept only in the page's state until the
 * person dismisses it, never in the query cache, and the list never has it.
 * The server validates every field again; the checks here only say early
 * what it would refuse.
 */
import { api } from '@/lib/api'

export type AgentTokenStatus = 'active' | 'expired' | 'revoked'

/** A stored token as `GET /api/agent-tokens` lists it (no secret, no hash). */
export interface AgentToken {
  id: string
  name: string
  /** `agent:<id>`: who the agent is in the audit log and the approval queue. */
  principal: string
  /** The users.yaml person the agent acts for. */
  user: string
  ventures: string[]
  status: AgentTokenStatus
  created_by: string
  created_at: string
  expires_at: string | null
  last_used_at: string | null
  revoked_at: string | null
  revoked_by: string | null
}

export interface AgentTokensResponse {
  tokens: AgentToken[]
  /** `features.agent_tokens`: off means no token works and none can be created. */
  enabled: boolean
}

/** `POST /api/agent-tokens`: the only response that ever carries the token. */
export interface CreatedAgentToken {
  token: string
  agent_token: AgentToken
  message?: string
}

export interface RevokedAgentToken {
  agent_token: AgentToken
  /** The agent's held writes that were still waiting, now withdrawn. */
  withdrawn_approvals: number
}

/** The create form as the person fills it in. */
export interface TokenForm {
  name: string
  user: string
  ventures: string[]
  /** Days as typed; empty means no expiry. */
  expiresInDays: string
}

export interface CreateAgentTokenBody {
  name: string
  user: string
  ventures: string[]
  expires_in_days: number | null
}

/** Same rule as `agent_tokens._NAME_RE`. */
export const NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/
export const MAX_EXPIRY_DAYS = 3650
export const MAX_VENTURES = 50
const MAX_USER_LENGTH = 254

export type FormProblem = 'name' | 'user' | 'ventures' | 'expiry'

export const EMPTY_FORM: TokenForm = { name: '', user: '', ventures: [], expiresInDays: '' }

/** Whole days 1..3650, or null for no expiry; undefined when the text isn't valid. */
function parseDays(raw: string): number | null | undefined {
  const text = raw.trim()
  if (!text) return null
  if (!/^\d+$/.test(text)) return undefined
  const days = Number(text)
  return days >= 1 && days <= MAX_EXPIRY_DAYS ? days : undefined
}

/** The fields the server would refuse (empty when the form can be sent). */
export function validateTokenForm(form: TokenForm): FormProblem[] {
  const problems: FormProblem[] = []
  if (!NAME_PATTERN.test(form.name.trim())) problems.push('name')
  const user = form.user.trim()
  if (!user || user.length > MAX_USER_LENGTH) problems.push('user')
  if (form.ventures.length === 0 || form.ventures.length > MAX_VENTURES) problems.push('ventures')
  if (parseDays(form.expiresInDays) === undefined) problems.push('expiry')
  return problems
}

/** The request body for a valid form. */
export function toCreateBody(form: TokenForm): CreateAgentTokenBody {
  return {
    name: form.name.trim(),
    user: form.user.trim(),
    ventures: [...new Set(form.ventures)],
    expires_in_days: parseDays(form.expiresInDays) ?? null,
  }
}

/** Toggle one venture in the form's selection. */
export function toggleVenture(form: TokenForm, key: string): TokenForm {
  const ventures = form.ventures.includes(key)
    ? form.ventures.filter((v) => v !== key)
    : [...form.ventures, key]
  return { ...form, ventures }
}

export function createAgentToken(form: TokenForm): Promise<CreatedAgentToken> {
  return api.post<CreatedAgentToken>('/agent-tokens', toCreateBody(form))
}

export function revokeAgentToken(id: string): Promise<RevokedAgentToken> {
  return api.delete<RevokedAgentToken>(`/agent-tokens/${encodeURIComponent(id)}`)
}

type ClipboardLike = Pick<Clipboard, 'writeText'>

function defaultClipboard(): ClipboardLike | undefined {
  return typeof navigator !== 'undefined' ? navigator.clipboard : undefined
}

/**
 * Copy text: the Clipboard API, else `fallback` (select the field and copy),
 * which plain-HTTP deployments need because the Clipboard API is HTTPS-only.
 * True when either worked.
 */
export async function copyText(
  text: string,
  fallback?: () => boolean,
  clipboard: ClipboardLike | undefined = defaultClipboard(),
): Promise<boolean> {
  if (clipboard && typeof clipboard.writeText === 'function') {
    try {
      await clipboard.writeText(text)
      return true
    } catch {
      // Permission denied or not focused: try the fallback.
    }
  }
  if (!fallback) return false
  try {
    return fallback()
  } catch {
    return false
  }
}

/* ------------------------------------------------------------------ */
/* Page state                                                          */
/* ------------------------------------------------------------------ */

export type CopyState = 'idle' | 'copied' | 'failed'

export interface TokensPageState {
  /** The token just created. Its secret lives only here, until the person dismisses it. */
  created: CreatedAgentToken | null
  copy: CopyState
  /** The token whose revocation is being confirmed. */
  revoking: AgentToken | null
}

export const INITIAL_TOKENS_STATE: TokensPageState = { created: null, copy: 'idle', revoking: null }

export type TokensPageAction =
  | { type: 'created'; created: CreatedAgentToken }
  | { type: 'copied'; ok: boolean }
  | { type: 'dismiss-created' }
  | { type: 'ask-revoke'; token: AgentToken }
  | { type: 'cancel-revoke' }
  | { type: 'revoked'; id: string }

export function tokensPageReducer(
  state: TokensPageState,
  action: TokensPageAction,
): TokensPageState {
  switch (action.type) {
    case 'created':
      return { ...state, created: action.created, copy: 'idle' }
    case 'copied':
      return state.created ? { ...state, copy: action.ok ? 'copied' : 'failed' } : state
    case 'dismiss-created':
      // Forget the secret: nothing can show it again.
      return { ...state, created: null, copy: 'idle' }
    case 'ask-revoke':
      return { ...state, revoking: action.token }
    case 'cancel-revoke':
      return { ...state, revoking: null }
    case 'revoked': {
      // A token revoked while its secret is still on screen is worthless: drop it too.
      const created = state.created?.agent_token.id === action.id ? null : state.created
      return {
        ...state,
        revoking: null,
        created,
        copy: created ? state.copy : 'idle',
      }
    }
  }
}
