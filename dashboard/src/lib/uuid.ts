/**
 * UUID generation that works in any browser context.
 *
 * `crypto.randomUUID()` is only available in Secure Contexts (HTTPS or
 * localhost). HTTP-served dashboards (typical for VPS-IP deployments) get
 * `undefined`, which crashes the page when called.
 *
 * `crypto.getRandomValues()` is available in all contexts and ships in every
 * evergreen browser, so we fall back to a 16-byte hex string when randomUUID
 * is missing. Format-compatible enough — callers only use it for IDs.
 */
export function safeRandomUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}
