/**
 * What the signed-in person may change, so pages hide or disable controls the
 * server would refuse (Codex audit, recommendation 7). This is UX only: the
 * server checks every request (`realize_core/security/venture_scope.py`).
 *
 * The session reports the role's permissions as the server resolves them
 * (custom roles from YAML included). The built-in table below mirrors
 * `realize_core/security/rbac.py` and is used only when a session doesn't
 * carry them.
 */

export type Permission =
  | 'pipeline:approve'
  | 'system:write'
  | 'system:manage'
  | 'system:delete'
  | 'agents:execute'

/** The parts of the signed-in user that decide what they may change. */
export interface Actor {
  role: string
  ventures?: string[] | null
  permissions?: string[] | null
}

const OPERATOR: readonly Permission[] = ['system:write', 'agents:execute', 'pipeline:approve']
const EVERYTHING: readonly Permission[] = [...OPERATOR, 'system:manage', 'system:delete']

/** Built-in roles (rbac.py), limited to the permissions the dashboard checks. */
const BUILTIN: Record<string, readonly Permission[]> = {
  owner: EVERYTHING,
  admin: EVERYTHING,
  operator: OPERATOR,
  user: ['system:write', 'agents:execute'],
  viewer: [],
  guest: [],
}

/** True when the actor's role grants `permission` (no actor: nothing). */
export function can(actor: Actor | null | undefined, permission: Permission): boolean {
  if (!actor) return false
  if (Array.isArray(actor.permissions)) return actor.permissions.includes(permission)
  return (BUILTIN[actor.role] ?? []).includes(permission)
}

/** True when the actor isn't limited to some ventures. */
export function isUnrestricted(actor: Actor | null | undefined): boolean {
  return !!actor && !Array.isArray(actor.ventures)
}

/** Why a control is off, in a sentence; null when the actor may use it. */
export type Gate = string | null

/**
 * Approving and rejecting held items (`pipeline:approve`). A venture-limited
 * person only ever sees their ventures' items, so the role alone decides.
 * (The approvals page words the reason in the person's language.)
 */
export function canDecide(actor: Actor | null | undefined): boolean {
  return can(actor, 'pipeline:approve')
}

function roleName(actor: Actor | null | undefined): string {
  return actor?.role || 'unknown'
}

/** Which venture changes the actor may make on the Ventures page, and why not. */
export interface VentureGates {
  canCreate: boolean
  canDelete: boolean
  /** One sentence explaining whatever is off; null when everything is allowed. */
  notice: Gate
}

/**
 * Creating a venture needs `system:manage` and a person not limited to some
 * ventures; deleting one needs `system:delete` (the server also checks the
 * venture is theirs). Both edit realize-os.yaml, so a read-only config turns
 * both off; the page's read-only notice explains that case.
 */
export function ventureGates(
  actor: Actor | null | undefined,
  configWritable: boolean,
): VentureGates {
  if (!configWritable) return { canCreate: false, canDelete: false, notice: null }
  const manage = can(actor, 'system:manage')
  const canCreate = manage && isUnrestricted(actor)
  const canDelete = can(actor, 'system:delete')
  const role = roleName(actor)
  let notice: Gate = null
  if (!manage && !canDelete)
    notice = `Your role (${role}) can’t create or delete ventures. Ask an owner or admin.`
  else if (!manage) notice = `Your role (${role}) can’t create ventures. Ask an owner or admin.`
  else if (!canCreate)
    notice =
      'You are limited to some ventures, so you can’t create a new one. Ask an owner or admin.'
  else if (!canDelete) notice = `Your role (${role}) can’t delete ventures. Ask an owner or admin.`
  return { canCreate, canDelete, notice }
}

/** Editing a venture's knowledge base (files, ingest): `system:write`. */
export function editKnowledgeGate(actor: Actor | null | undefined): Gate {
  if (can(actor, 'system:write')) return null
  return `View only: your role (${roleName(actor)}) can read the knowledge base but not change it.`
}

/** Connecting providers and integrations (Setup): `system:manage` and every venture. */
export function setupGate(actor: Actor | null | undefined): Gate {
  if (can(actor, 'system:manage') && isUnrestricted(actor)) return null
  return 'Ask an owner or admin to connect providers and create the first venture.'
}
