import {
  useEffect,
  useId,
  useReducer,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'
import {
  AlertCircle,
  AlertTriangle,
  Building2,
  Check,
  Copy,
  ExternalLink,
  Info,
  KeyRound,
  Plus,
  RefreshCw,
} from 'lucide-react'
import { useApi, useInvalidateApi } from '@/hooks/use-api'
import { useAuth } from '@/hooks/use-auth'
import { useVenture, type VentureSummary } from '@/hooks/use-venture'
import { useLocale } from '@/components/locale-provider'
import { useToast } from '@/components/ui/toast'
import { TitleBlock } from '@/components/ui/title-block'
import { Panel } from '@/components/ui/panel'
import { Badge, type Tone } from '@/components/ui/badge'
import { Button, IconButton } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { SkeletonCard } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { canManageAgentTokens } from '@/lib/permissions'
import {
  EMPTY_FORM,
  INITIAL_TOKENS_STATE,
  MAX_EXPIRY_DAYS,
  copyText,
  createAgentToken,
  revokeAgentToken,
  toggleVenture,
  tokensPageReducer,
  validateTokenForm,
  type AgentToken,
  type AgentTokensResponse,
  type AgentTokenStatus,
  type CopyState,
  type CreatedAgentToken,
  type FormProblem,
  type TokenForm,
  type TokensPageState,
} from '@/lib/agent-tokens'
import { agentTokensText, type AgentTokensText } from '@/lib/agent-tokens-text'

/** The connect guide: how an agent uses a token, and what it may do. */
export const CONNECT_GUIDE_URL =
  'https://github.com/SufZen/RealizeOS-5/blob/main/docs/connect-your-agent.md#agent-tokens-one-agent-one-clients-brain'

const STATUS_TONE: Record<AgentTokenStatus, Tone> = {
  active: 'success',
  expired: 'neutral',
  revoked: 'danger',
}

function formatWhen(iso: string | null, language: string): string {
  if (!iso) return ''
  const t = new Date(iso)
  if (Number.isNaN(t.getTime())) return iso
  return t.toLocaleString(language === 'he' ? 'he-IL' : undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

function errorDetail(err: unknown): string {
  const detail = err instanceof Error ? err.message.trim() : ''
  return detail || String(err || '')
}

/**
 * Agent tokens (STORY-37): one outside agent, one client's brain. Owners and
 * admins with every venture only, like `realize_api/routes/agent_tokens.py`;
 * the nav hides it from everyone else, and a direct visit says why.
 */
export default function AgentTokensPage() {
  const { user } = useAuth()
  const { language } = useLocale()
  const text = agentTokensText(language)
  if (!canManageAgentTokens(user)) return <NotAllowed text={text} />
  return <AgentTokensManager defaultUser={user?.user_id ?? ''} />
}

function NotAllowed({ text }: { text: AgentTokensText }) {
  return (
    <div className="mx-auto max-w-[960px]">
      <TitleBlock
        title={text.title}
        crumbs={[{ label: text.settings, to: '/settings' }, { label: text.title }]}
      />
      <p
        data-gate="agent-tokens"
        className="m-0 flex items-start gap-2 text-[13px] text-muted-foreground"
      >
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-blue-400" aria-hidden />
        <span>{text.notAllowed}</span>
      </p>
    </div>
  )
}

function AgentTokensManager({ defaultUser }: { defaultUser: string }) {
  const { language } = useLocale()
  const text = agentTokensText(language)
  const toast = useToast()
  const { ventures } = useVenture()
  const { data, loading, error } = useApi<AgentTokensResponse>('/agent-tokens')
  const invalidate = useInvalidateApi()
  const [state, dispatch] = useReducer(tokensPageReducer, INITIAL_TOKENS_STATE)
  const [form, setForm] = useState<TokenForm>({ ...EMPTY_FORM, user: defaultUser })
  const [showProblems, setShowProblems] = useState(false)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [revokeBusy, setRevokeBusy] = useState(false)

  async function create() {
    if (validateTokenForm(form).length > 0) {
      setShowProblems(true)
      return
    }
    setCreating(true)
    setCreateError(null)
    try {
      const created = await createAgentToken(form)
      dispatch({ type: 'created', created })
      setForm({ ...EMPTY_FORM, user: form.user })
      setShowProblems(false)
    } catch (err) {
      setCreateError(text.createFailed(errorDetail(err)))
    } finally {
      setCreating(false)
      invalidate('/agent-tokens')
    }
  }

  async function copy(fallback: () => boolean) {
    if (!state.created) return
    dispatch({ type: 'copied', ok: await copyText(state.created.token, fallback) })
  }

  async function confirmRevoke() {
    const token = state.revoking
    if (!token) return
    setRevokeBusy(true)
    try {
      const res = await revokeAgentToken(token.id)
      dispatch({ type: 'revoked', id: token.id })
      toast.success(text.revoked(token.name, res.withdrawn_approvals ?? 0))
      // Withdrawn writes leave the approval queue too.
      if (res.withdrawn_approvals) invalidate('/approvals')
    } catch (err) {
      dispatch({ type: 'cancel-revoke' })
      toast.error(text.revokeFailed(errorDetail(err)))
    } finally {
      setRevokeBusy(false)
      invalidate('/agent-tokens')
    }
  }

  return (
    <AgentTokensView
      text={text}
      language={language}
      tokens={data?.tokens ?? []}
      enabled={data?.enabled !== false}
      loading={loading}
      error={error ? text.loadFailed : null}
      ventures={ventures}
      form={form}
      onFormChange={(next) => {
        setForm(next)
        setCreateError(null)
      }}
      problems={showProblems ? validateTokenForm(form) : []}
      createError={createError}
      creating={creating}
      onCreate={create}
      state={state}
      onCopy={copy}
      onDismissCreated={() => dispatch({ type: 'dismiss-created' })}
      onAskRevoke={(token) => dispatch({ type: 'ask-revoke', token })}
      onCancelRevoke={() => dispatch({ type: 'cancel-revoke' })}
      onConfirmRevoke={confirmRevoke}
      revokeBusy={revokeBusy}
      onRefresh={() => invalidate('/agent-tokens')}
    />
  )
}

export interface AgentTokensViewProps {
  text: AgentTokensText
  language: string
  tokens: AgentToken[]
  /** `features.agent_tokens`. */
  enabled: boolean
  loading: boolean
  error: string | null
  /** Ventures the signed-in person may see: the only ones a token can name. */
  ventures: VentureSummary[]
  form: TokenForm
  onFormChange: (form: TokenForm) => void
  /** Fields to flag (after a send attempt). */
  problems: FormProblem[]
  createError: string | null
  creating: boolean
  onCreate: () => void
  state: TokensPageState
  /** Copy the new token; `fallback` selects the field and copies (plain-HTTP servers). */
  onCopy: (fallback: () => boolean) => void
  onDismissCreated: () => void
  onAskRevoke: (token: AgentToken) => void
  onCancelRevoke: () => void
  onConfirmRevoke: () => void
  revokeBusy: boolean
  onRefresh: () => void
}

/** The agent tokens page as it renders, from plain props. */
export function AgentTokensView({
  text,
  language,
  tokens,
  enabled,
  loading,
  error,
  ventures,
  form,
  onFormChange,
  problems,
  createError,
  creating,
  onCreate,
  state,
  onCopy,
  onDismissCreated,
  onAskRevoke,
  onCancelRevoke,
  onConfirmRevoke,
  revokeBusy,
  onRefresh,
}: AgentTokensViewProps) {
  return (
    <div className="mx-auto max-w-[960px]">
      <TitleBlock
        title={text.title}
        description={text.description}
        crumbs={[{ label: text.settings, to: '/settings' }, { label: text.title }]}
        actions={
          <>
            <a
              href={CONNECT_GUIDE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="rz-btn rz-btn--ghost rz-btn--sm"
            >
              <ExternalLink aria-hidden />
              {text.guide}
            </a>
            <IconButton label={text.refresh} onClick={onRefresh}>
              <RefreshCw />
            </IconButton>
          </>
        }
      />

      <div className="grid gap-6">
        {!enabled && (
          <p
            role="status"
            data-flag="agent_tokens"
            className="m-0 flex items-start gap-2 rounded-[10px] border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-[13px] text-amber-400"
          >
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>{text.disabled}</span>
          </p>
        )}

        {state.created && (
          <CreatedTokenNotice
            created={state.created}
            copy={state.copy}
            text={text}
            onCopy={onCopy}
            onDismiss={onDismissCreated}
          />
        )}

        <CreateTokenForm
          text={text}
          ventures={ventures}
          form={form}
          onChange={onFormChange}
          problems={problems}
          error={createError}
          busy={creating}
          disabled={!enabled}
          onSubmit={onCreate}
        />

        <Panel
          title={
            <span className="inline-flex items-center gap-2">
              {text.listTitle}
              {!loading && !error && <Badge className="tabular">{tokens.length}</Badge>}
            </span>
          }
          flush
        >
          {loading ? (
            <div className="grid gap-3 p-4" aria-busy="true" aria-label={text.loading}>
              <SkeletonCard />
            </div>
          ) : error ? (
            <p role="alert" className="m-0 flex items-start gap-2 p-4 text-sm text-red-400">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              <span>{error}</span>
            </p>
          ) : tokens.length === 0 ? (
            <EmptyState title={text.empty} body={text.emptyBody} />
          ) : (
            <ul className="m-0 list-none p-0">
              {tokens.map((token) => (
                <TokenRow
                  key={token.id}
                  token={token}
                  text={text}
                  language={language}
                  onRevoke={() => onAskRevoke(token)}
                />
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <ConfirmDialog
        isOpen={!!state.revoking}
        title={state.revoking ? text.revokeTitle(state.revoking.name) : ''}
        message={<p className="m-0 text-sm text-muted-foreground">{text.revokeBody}</p>}
        confirmText={revokeBusy ? `${text.revokeConfirm}…` : text.revokeConfirm}
        cancelText={text.cancel}
        isDestructive
        onConfirm={() => {
          if (!revokeBusy) onConfirmRevoke()
        }}
        onCancel={onCancelRevoke}
      />
    </div>
  )
}

/** The token, once: a copy button, and a plain warning that it won't be shown again. */
export function CreatedTokenNotice({
  created,
  copy,
  text,
  onCopy,
  onDismiss,
}: {
  created: CreatedAgentToken
  copy: CopyState
  text: AgentTokensText
  onCopy: (fallback: () => boolean) => void
  onDismiss: () => void
}) {
  const inputId = useId()
  const noteId = `${inputId}-note`
  const field = useRef<HTMLInputElement>(null)
  const tokenId = created.agent_token.id

  // A new token is where the person needs to be: bring it into view, selected.
  useEffect(() => {
    field.current?.focus()
  }, [tokenId])

  function selectAndCopy(): boolean {
    const el = field.current
    if (!el) return false
    el.focus()
    el.select()
    return document.execCommand('copy')
  }

  return (
    <Panel
      data-created-token={created.agent_token.id}
      aria-label={text.createdTitle}
      title={
        <span className="inline-flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-subtle-foreground" aria-hidden />
          {text.createdTitle}
        </span>
      }
      footer={
        <div className="flex justify-end">
          <Button variant="primary" onClick={onDismiss}>
            <Check aria-hidden />
            {text.done}
          </Button>
        </div>
      }
    >
      <div className="grid gap-3">
        <p
          id={noteId}
          data-once
          className="m-0 flex items-start gap-2 rounded-[7px] border border-amber-400/30 bg-amber-400/10 px-3 py-2 text-[13px] text-amber-400"
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>{text.createdNote}</span>
        </p>
        <div className="rz-field">
          <label htmlFor={inputId} className="rz-label">
            {text.tokenLabel(created.agent_token.name)}
          </label>
          <div className="flex gap-2">
            <input
              ref={field}
              id={inputId}
              readOnly
              value={created.token}
              dir="ltr"
              spellCheck={false}
              autoComplete="off"
              aria-describedby={noteId}
              onFocus={(e) => e.currentTarget.select()}
              className="rz-input min-w-0 flex-1 font-mono"
            />
            <Button onClick={() => onCopy(selectAndCopy)}>
              {copy === 'copied' ? <Check aria-hidden /> : <Copy aria-hidden />}
              {copy === 'copied' ? text.copied : text.copy}
            </Button>
          </div>
          <span className="sr-only" role="status">
            {copy === 'copied' ? text.copied : ''}
          </span>
          {copy === 'failed' ? (
            <span className="rz-error" role="alert">
              <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
              {text.copyFailed}
            </span>
          ) : (
            <span className="rz-help">
              {text.usage}{' '}
              <code dir="ltr" className="font-mono">
                Authorization: Bearer &lt;token&gt;
              </code>
              , {text.usageAfter}
            </span>
          )}
        </div>
      </div>
    </Panel>
  )
}

function CreateTokenForm({
  text,
  ventures,
  form,
  onChange,
  problems,
  error,
  busy,
  disabled,
  onSubmit,
}: {
  text: AgentTokensText
  ventures: VentureSummary[]
  form: TokenForm
  onChange: (form: TokenForm) => void
  problems: FormProblem[]
  error: string | null
  busy: boolean
  disabled: boolean
  onSubmit: () => void
}) {
  const id = useId()
  const has = (p: FormProblem) => problems.includes(p)
  const note = (p: FormProblem) => `${id}-${p}`

  function submit(e: FormEvent) {
    e.preventDefault()
    if (!disabled && !busy) onSubmit()
  }

  return (
    <Panel title={text.createTitle}>
      <form className="grid gap-4" onSubmit={submit} noValidate aria-label={text.createTitle}>
        <div className="grid items-start gap-4 sm:grid-cols-2">
          <TextField
            id={`${id}-name`}
            noteId={note('name')}
            label={text.nameLabel}
            help={text.nameHelp}
            problem={has('name') ? text.problems.name : null}
            value={form.name}
            disabled={disabled}
            maxLength={64}
            onChange={(name) => onChange({ ...form, name })}
          />
          <TextField
            id={`${id}-user`}
            noteId={note('user')}
            type="email"
            label={text.userLabel}
            help={text.userHelp}
            problem={has('user') ? text.problems.user : null}
            value={form.user}
            disabled={disabled}
            maxLength={254}
            onChange={(user) => onChange({ ...form, user })}
          />
        </div>

        <fieldset className="m-0 grid gap-1.5 border-0 p-0" disabled={disabled}>
          <legend className="rz-label mb-1.5 p-0">{text.venturesLabel}</legend>
          {ventures.length === 0 ? (
            <p className="m-0 text-[13px] text-muted-foreground">{text.noVentures}</p>
          ) : (
            <div className="flex flex-wrap gap-2" aria-describedby={note('ventures')}>
              {ventures.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  className="rz-chip"
                  aria-pressed={form.ventures.includes(v.key)}
                  onClick={() => onChange(toggleVenture(form, v.key))}
                >
                  <Building2 aria-hidden />
                  <bdi>{v.name || v.key}</bdi>
                </button>
              ))}
            </div>
          )}
          <FieldNote
            id={note('ventures')}
            help={text.venturesHelp}
            problem={has('ventures') ? text.problems.ventures : null}
          />
        </fieldset>

        <div className="sm:max-w-[240px]">
          <TextField
            id={`${id}-expiry`}
            noteId={note('expiry')}
            type="number"
            label={text.expiryLabel}
            help={text.expiryHelp}
            problem={has('expiry') ? text.problems.expiry : null}
            value={form.expiresInDays}
            disabled={disabled}
            min={1}
            max={MAX_EXPIRY_DAYS}
            onChange={(expiresInDays) => onChange({ ...form, expiresInDays })}
          />
        </div>

        {error && (
          <p
            role="alert"
            dir="auto"
            className="m-0 flex items-start gap-2 rounded-[7px] border border-red-400/30 bg-red-400/10 px-3 py-2 text-[13px] text-red-400"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
            <span className="min-w-0 break-words">{error}</span>
          </p>
        )}

        <div className="flex justify-end">
          <Button type="submit" variant="primary" busy={busy} disabled={disabled}>
            <Plus aria-hidden />
            {text.create}
          </Button>
        </div>
      </form>
    </Panel>
  )
}

function FieldNote({ id, help, problem }: { id: string; help: string; problem: string | null }) {
  return problem ? (
    <span id={id} className="rz-error" role="alert">
      <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
      {problem}
    </span>
  ) : (
    <span id={id} className="rz-help">
      {help}
    </span>
  )
}

function TextField({
  id,
  noteId,
  label,
  help,
  problem,
  value,
  onChange,
  type = 'text',
  disabled,
  maxLength,
  min,
  max,
}: {
  id: string
  noteId: string
  label: string
  help: string
  problem: string | null
  value: string
  onChange: (value: string) => void
  type?: 'text' | 'email' | 'number'
  disabled?: boolean
  maxLength?: number
  min?: number
  max?: number
}) {
  return (
    <div className="rz-field">
      <label htmlFor={id} className="rz-label">
        {label}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        maxLength={maxLength}
        min={min}
        max={max}
        inputMode={type === 'number' ? 'numeric' : undefined}
        dir="ltr"
        spellCheck={false}
        autoComplete="off"
        aria-describedby={noteId}
        aria-invalid={problem ? true : undefined}
        className={cn('rz-input', problem && 'rz-nudge')}
      />
      <FieldNote id={noteId} help={help} problem={problem} />
    </div>
  )
}

/** One token: who it acts for, where, its dates, and Revoke while it still works. */
export function TokenRow({
  token,
  text,
  language,
  onRevoke,
}: {
  token: AgentToken
  text: AgentTokensText
  language: string
  onRevoke: () => void
}) {
  const live = token.status !== 'revoked'
  return (
    <li
      data-token={token.id}
      className="grid gap-3 border-b border-border px-4 py-3.5 last:border-b-0 sm:flex sm:items-start sm:gap-4"
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h4 className="m-0 text-[15px] font-semibold text-foreground">
            <bdi>{token.name}</bdi>
          </h4>
          <Badge tone={STATUS_TONE[token.status]} dot={token.status === 'active'}>
            {text.status[token.status]}
          </Badge>
          <code dir="ltr" className="text-[11px] text-subtle-foreground">
            {token.id}
          </code>
        </div>
        <dl className="m-0 mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-xs text-subtle-foreground">
          <Meta label={text.actsFor}>
            <bdi>{token.user}</bdi>
          </Meta>
          <Meta label={text.created}>{formatWhen(token.created_at, language)}</Meta>
          <Meta label={text.expires}>
            {token.expires_at ? formatWhen(token.expires_at, language) : text.noExpiry}
          </Meta>
          <Meta label={text.lastUsed}>
            {token.last_used_at ? formatWhen(token.last_used_at, language) : text.notUsed}
          </Meta>
          {token.revoked_at && (
            <Meta label={text.revokedOn}>{formatWhen(token.revoked_at, language)}</Meta>
          )}
        </dl>
        <ul
          className="m-0 mt-2 flex list-none flex-wrap gap-1.5 p-0"
          aria-label={text.venturesLabel}
        >
          {token.ventures.map((v) => (
            <li key={v}>
              <Badge outline>
                <Building2 className="h-3 w-3" aria-hidden />
                <bdi>{v}</bdi>
              </Badge>
            </li>
          ))}
        </ul>
      </div>
      {live && (
        <Button size="sm" variant="ghost" className="justify-self-start" onClick={onRevoke}>
          {text.revoke}
        </Button>
      )}
    </li>
  )
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="inline-flex min-w-0 gap-1">
      <dt>{label}:</dt>
      <dd className="m-0 min-w-0 break-words text-muted-foreground">{children}</dd>
    </div>
  )
}
