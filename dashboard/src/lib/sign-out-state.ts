/**
 * Whether this tab signed out on purpose. After a deliberate sign-out the
 * sign-in page must not send the next person back to the previous person's
 * page, so the auth guard redirects to plain `/login` (a session that merely
 * expired still keeps `next`, to return the same person where they were).
 * A successful sign-in clears it.
 */
let signedOutOnPurpose = false

export function markSignedOut(): void {
  signedOutOnPurpose = true
}

export function clearSignedOut(): void {
  signedOutOnPurpose = false
}

export function wasSignedOut(): boolean {
  return signedOutOnPurpose
}

/** Where the auth guard sends someone with no session: plain `/login` after a deliberate sign-out. */
export function loginRedirect(pathname: string, search: string): string {
  if (signedOutOnPurpose) return '/login'
  return `/login?next=${encodeURIComponent(`${pathname}${search}`)}`
}
