import { LogOut } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ShellText } from '@/lib/shell-text'

/**
 * Ends the session, in the sidebar next to language and theme. Shows who is
 * signed in, so a shared screen says whose dashboard it is.
 */
export function SignOutButton({
  text,
  userId,
  busy,
  onSignOut,
}: {
  text: ShellText
  userId?: string | null
  busy?: boolean
  onSignOut: () => void
}) {
  return (
    <button
      type="button"
      data-action="sign-out"
      onClick={onSignOut}
      disabled={busy}
      aria-busy={busy || undefined}
      title={userId ? text.signedInAs(userId) : undefined}
      className={cn(
        'flex items-center gap-2.5 w-full h-8 rounded-[5px] px-2.5 text-[13px]',
        'text-muted-foreground hover:text-foreground hover:bg-surface-700/60',
        'transition-colors disabled:opacity-60',
      )}
    >
      <LogOut className="h-4 w-4 shrink-0 rtl:-scale-x-100" aria-hidden />
      <span>{text.signOut}</span>
      {userId && (
        <bdi className="ms-auto min-w-0 truncate text-xs text-subtle-foreground">{userId}</bdi>
      )}
    </button>
  )
}
