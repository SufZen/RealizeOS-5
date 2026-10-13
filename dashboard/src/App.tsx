import { useState, useEffect, useMemo, lazy, Suspense, Component, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard,
  Briefcase,
  Activity,
  Sparkles,
  ShieldCheck,
  Settings,
  Menu,
  X,
  MessageCircle,
  Wrench,
  BookOpen,
  Plug,
  GitBranch,
  FileCode2,
  Route as RouteIcon,
  Puzzle,
  Target,
  Brain,
  Search,
  Moon,
  Sun,
  Languages,
  KeyRound,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ThemeProvider } from '@/components/theme-provider'
import { ThemeToggle } from '@/components/theme-toggle'
import { TourProvider } from '@/components/tour-provider'
import { ToastProvider } from '@/components/ui/toast'
import { Skeleton, SkeletonCard } from '@/components/ui/skeleton'
import { AuthProvider, useAuth } from '@/hooks/use-auth'
import { api } from '@/lib/api'
import { VentureProvider } from '@/hooks/use-venture'
import { VentureSwitcher } from '@/components/venture-switcher'
import { LocaleProvider } from '@/components/locale-provider'
import { LocaleToggle } from '@/components/locale-toggle'
import AuthGuard from '@/components/auth-guard'
import { useApi } from '@/hooks/use-api'
import { useTheme } from '@/components/theme-provider'
import { useLocale } from '@/components/locale-provider'
import { CommandPalette, type Command } from '@/components/ui/command-palette'
import { Kbd } from '@/components/ui/badge'
import { BrandMark } from '@/components/ui/brand-mark'
import { canOpenPage } from '@/lib/permissions'

const OverviewPage = lazy(() => import('@/pages/overview'))
const ChatPage = lazy(() => import('@/pages/chat-page'))
const VenturesListPage = lazy(() => import('@/pages/ventures-list'))
const VentureDetailPage = lazy(() => import('@/pages/venture-detail'))
const ActivityPage = lazy(() => import('@/pages/activity-page'))
const AgentDetailPage = lazy(() => import('@/pages/agent-detail'))
const ApprovalsPage = lazy(() => import('@/pages/approvals-page'))
const EvolutionPage = lazy(() => import('@/pages/evolution-page'))
const SettingsPage = lazy(() => import('@/pages/settings-page'))
const ToolsPage = lazy(() => import('@/pages/tools-page'))
const SkillsPage = lazy(() => import('@/pages/skills-page'))
const SetupPage = lazy(() => import('@/pages/setup-page'))
const PipelineBuilderPage = lazy(() => import('@/pages/pipeline-builder'))
const WorkflowEditorPage = lazy(() => import('@/pages/workflow-editor'))
const RoutingPage = lazy(() => import('@/pages/routing-page'))
const IntegrationsPage = lazy(() => import('@/pages/integrations-page'))
const DocsPage = lazy(() => import('@/pages/docs-page'))
const LoginPage = lazy(() => import('@/pages/login-page'))
const MissionsPage = lazy(() => import('@/pages/missions-page'))
const KnowledgeMapPage = lazy(() => import('@/pages/knowledge-map-page'))
const DreamInboxPage = lazy(() => import('@/pages/dream-inbox-page'))
const DesignPage = lazy(() => import('@/pages/design-page'))
const AgentTokensPage = lazy(() => import('@/pages/agent-tokens-page'))

import OnboardingWizard, {
  isOnboardingComplete,
  markOnboardingComplete,
  serverHasAiProvider,
} from '@/components/onboarding-wizard'

interface NavItem {
  to: string
  icon: LucideIcon
  label: string
  /** Extra words the command palette matches (synonyms, Hebrew). */
  keywords?: string
}

const navGroups: { label: string; items: NavItem[] }[] = [
  {
    label: 'Core',
    items: [
      { to: '/', icon: LayoutDashboard, label: 'Overview' },
      { to: '/chat', icon: MessageCircle, label: 'Chat' },
      { to: '/ventures', icon: Briefcase, label: 'Ventures' },
    ],
  },
  {
    label: 'Build',
    items: [
      { to: '/skills', icon: BookOpen, label: 'Skills' },
      { to: '/pipelines', icon: GitBranch, label: 'Pipelines' },
      { to: '/workflows', icon: FileCode2, label: 'Workflows' },
    ],
  },
  {
    label: 'Monitor',
    items: [
      { to: '/activity', icon: Activity, label: 'Activity' },
      { to: '/approvals', icon: ShieldCheck, label: 'Approvals' },
      { to: '/evolution', icon: Sparkles, label: 'Evolution' },
      { to: '/routing', icon: RouteIcon, label: 'Routing' },
    ],
  },
  {
    label: 'FABRIC',
    items: [
      { to: '/missions', icon: Target, label: 'Missions' },
      { to: '/knowledge', icon: Brain, label: 'Knowledge' },
      { to: '/dreams', icon: Sparkles, label: 'Dreams' },
    ],
  },
  {
    label: 'Configure',
    items: [
      { to: '/tools', icon: Wrench, label: 'Tools' },
      { to: '/integrations', icon: Puzzle, label: 'Integrations' },
      { to: '/docs', icon: BookOpen, label: 'Docs' },
      { to: '/setup', icon: Plug, label: 'Setup' },
      { to: '/settings', icon: Settings, label: 'Settings' },
      {
        to: '/settings/agent-tokens',
        icon: KeyRound,
        label: 'Agent tokens',
        keywords: 'mcp outside agent connect claude chatgpt cursor api key revoke טוקן סוכן',
      },
    ],
  },
]

/** Links that stay active only on their own page, not on the pages under them. */
const EXACT_NAV = new Set(['/', '/settings'])

/**
 * Nav groups the signed-in user may see: venture-limited users lose
 * system-wide pages, and only owners and admins with every venture get agent
 * tokens (`canOpenPage`). The server checks every request anyway.
 */
function useVisibleNav() {
  const { user } = useAuth()
  return useMemo(
    () =>
      navGroups
        .map((group) => ({
          ...group,
          items: group.items.filter((item) => canOpenPage(user, item.to)),
        }))
        .filter((group) => group.items.length > 0),
    [user],
  )
}

/** Approvals held for a person, shown on the nav so held work is never out of sight. */
function useHeldCount(): number {
  const { data } = useApi<{ approvals: { status: string }[] }>('/approvals?status=pending')
  return (data?.approvals ?? []).filter((a) => a.status === 'pending').length
}

function NavContent({ onNavigate }: { onNavigate?: () => void }) {
  const groups = useVisibleNav()
  const held = useHeldCount()

  return (
    <nav className="flex flex-col gap-4 flex-1" data-tour="sidebar" aria-label="Main">
      {groups.map((group) => (
        <div key={group.label}>
          <span className="px-2.5 mb-1 block text-xs font-medium text-subtle-foreground">
            {group.label}
          </span>
          <ul className="m-0 p-0 list-none grid gap-px">
            {group.items.map(({ to, icon: Icon, label }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={EXACT_NAV.has(to)}
                  viewTransition
                  onClick={onNavigate}
                  data-tour={`nav-${label.toLowerCase()}`}
                  className={({ isActive }) =>
                    cn(
                      'group relative flex items-center gap-2.5 rounded-[5px] h-8 px-2.5 text-[13px] no-underline transition-colors',
                      isActive
                        ? 'bg-surface-700 text-foreground font-medium'
                        : 'text-muted-foreground hover:bg-surface-700/60 hover:text-foreground',
                    )
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && (
                        <span
                          aria-hidden
                          className="absolute inset-y-1.5 -start-px w-[3px] rounded-full bg-brand-400"
                        />
                      )}
                      <Icon
                        className={cn(
                          'h-4 w-4 shrink-0',
                          isActive
                            ? 'text-foreground'
                            : 'text-subtle-foreground group-hover:text-foreground',
                        )}
                      />
                      <span className="truncate">{label}</span>
                      {to === '/approvals' && held > 0 && (
                        <span
                          className="ms-auto rz-badge rz-badge--accent tabular"
                          aria-label={`${held} held for you`}
                        >
                          {held}
                        </span>
                      )}
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function Logo() {
  return <BrandMark size={24} className="px-1.5" />
}

function SearchButton({ onOpen }: { onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-2 h-8 rounded-[5px] border border-border bg-background/40 px-2.5 text-[13px] text-subtle-foreground transition-colors hover:border-border-strong hover:text-foreground"
    >
      <Search className="h-3.5 w-3.5" aria-hidden />
      <span>Search</span>
      <span className="ms-auto">
        <Kbd>Ctrl K</Kbd>
      </span>
    </button>
  )
}

function SidebarBody({ onNavigate, onSearch }: { onNavigate?: () => void; onSearch: () => void }) {
  return (
    <>
      <VentureSwitcher />
      <div className="mb-4 -mt-2">
        <SearchButton onOpen={onSearch} />
      </div>
      <NavContent onNavigate={onNavigate} />
      <div className="mt-6 pt-3 border-t border-border grid gap-px" data-tour="theme-toggle">
        <LocaleToggle />
        <ThemeToggle />
      </div>
    </>
  )
}

function DesktopSidebar({ onSearch }: { onSearch: () => void }) {
  return (
    <aside className="hidden md:flex w-[248px] shrink-0 flex-col overflow-y-auto border-e border-border bg-surface-950 px-3 py-4">
      <div className="mb-5">
        <Logo />
      </div>
      <SidebarBody onSearch={onSearch} />
    </aside>
  )
}

function MobileHeader({ onToggle, onSearch }: { onToggle: () => void; onSearch: () => void }) {
  return (
    <header className="flex md:hidden items-center gap-1 border-b border-border bg-surface-950 fx-glass px-3 h-14">
      <Logo />
      <div className="ms-auto flex items-center">
        <button onClick={onSearch} className="rz-icon-btn" aria-label="Search">
          <Search />
        </button>
        <button onClick={onToggle} className="rz-icon-btn" aria-label="Open navigation">
          <Menu />
        </button>
      </div>
    </header>
  )
}

function MobileSheet({
  open,
  onClose,
  onSearch,
}: {
  open: boolean
  onClose: () => void
  onSearch: () => void
}) {
  useEffect(() => {
    if (!open) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <>
      <div
        className="fixed inset-0 z-40 rz-fade"
        style={{ background: 'var(--rz-overlay)' }}
        onClick={onClose}
      />
      <div
        className="fixed inset-y-0 start-0 z-50 flex w-[280px] flex-col overflow-y-auto bg-surface-950 border-e border-border px-3 py-4 shadow-xl rz-animate-slide-in-right"
        role="dialog"
        aria-modal="true"
        aria-label="Navigation menu"
      >
        <div className="flex items-center justify-between mb-5">
          <Logo />
          <button onClick={onClose} className="rz-icon-btn" aria-label="Close navigation">
            <X />
          </button>
        </div>
        <SidebarBody
          onNavigate={onClose}
          onSearch={() => {
            onClose()
            onSearch()
          }}
        />
      </div>
    </>
  )
}

/** Ctrl/Cmd K: every page this person may open, plus the few global preferences. */
function useShellCommands(): Command[] {
  const groups = useVisibleNav()
  const navigate = useNavigate()
  const { resolved, setTheme } = useTheme()
  const { override, setOverride } = useLocale()
  return useMemo(
    () => [
      ...groups.flatMap((g) =>
        g.items.map((item) => ({
          id: `go-${item.to}`,
          group: 'Go to',
          label: item.label,
          icon: item.icon,
          hint: g.label,
          keywords: item.keywords,
          run: () => navigate(item.to, { viewTransition: true }),
        })),
      ),
      {
        id: 'theme',
        group: 'Preferences',
        label: resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode',
        icon: resolved === 'dark' ? Sun : Moon,
        run: () => setTheme(resolved === 'dark' ? 'light' : 'dark'),
      },
      {
        id: 'locale',
        group: 'Preferences',
        label: override === 'he' ? 'Switch to English' : 'Switch to Hebrew (עברית)',
        keywords: 'language direction rtl עברית',
        icon: Languages,
        run: () => setOverride(override === 'he' ? 'en' : 'he'),
      },
    ],
    [groups, navigate, resolved, setTheme, override, setOverride],
  )
}

function PageSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Skeleton className="h-6 w-6 rounded" />
        <Skeleton className="h-8 w-48" />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <SkeletonCard />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    </div>
  )
}

function NotFoundPage() {
  return (
    <div className="flex flex-1 items-center justify-center p-8 relative">
      <div className="rz-drafting-grid absolute inset-0 pointer-events-none [mask-image:radial-gradient(ellipse_at_center,black_20%,transparent_70%)]" />
      <div className="text-center max-w-md relative z-10 rz-enter">
        <div className="text-[3.5rem] leading-none font-medium tracking-tight tabular text-foreground mb-4">
          404
        </div>
        <h2 className="text-lg font-semibold text-foreground mb-2">This page doesn’t exist</h2>
        <p className="text-sm text-muted-foreground mb-5">
          The link may be old, or the page was moved. Use Search to find what you need.
        </p>
        <NavLink to="/" viewTransition className="rz-btn rz-btn--primary">
          Go to Overview
        </NavLink>
      </div>
    </div>
  )
}

class ErrorBoundary extends Component<
  { children: ReactNode; resetKey?: string },
  { hasError: boolean; error: string }
> {
  constructor(props: { children: ReactNode; resetKey?: string }) {
    super(props)
    this.state = { hasError: false, error: '' }
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message }
  }
  componentDidUpdate(prevProps: { resetKey?: string }) {
    // Auto-reset when navigation changes (user clicks a different page)
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: '' })
    }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="text-center max-w-md">
            <h2 className="text-lg font-semibold text-foreground mb-2">
              This page stopped working
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              {this.state.error || 'An unexpected error occurred.'}
            </p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => this.setState({ hasError: false, error: '' })}
                className="rz-btn rz-btn--primary"
              >
                Retry
              </button>
              <button onClick={() => window.location.reload()} className="rz-btn rz-btn--secondary">
                Reload page
              </button>
            </div>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function ErrorBoundaryWithLocation({ children }: { children: ReactNode }) {
  const location = useLocation()
  return <ErrorBoundary resetKey={location.pathname}>{children}</ErrorBoundary>
}

function ShellPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const commands = useShellCommands()
  return <CommandPalette commands={commands} open={open} onOpenChange={onOpenChange} />
}

function AuthenticatedShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const { user } = useAuth()
  const [showOnboarding, setShowOnboarding] = useState(!isOnboardingComplete())
  // 'unknown' until the server says whether setup was already done (QA 5.14 D-1:
  // the wizard used to appear in every new browser, even on a configured server).
  const [serverSetup, setServerSetup] = useState<'unknown' | 'done' | 'needed'>('unknown')

  // Don't show onboarding until the user is signed in — onboarding writes setup state
  // for the active deployment, not the anonymous visitor. Users limited to some
  // ventures can't change deployment setup, so they never get it.
  const wantsOnboarding = showOnboarding && !!user && !Array.isArray(user.ventures)

  useEffect(() => {
    if (!wantsOnboarding) return
    let current = true
    api
      .get<{ connections: { category: string; configured: boolean }[] }>('/setup/connections')
      .then((data) => {
        if (!current) return
        const done = serverHasAiProvider(data.connections ?? [])
        if (done) markOnboardingComplete()
        setServerSetup(done ? 'done' : 'needed')
      })
      .catch(() => current && setServerSetup('needed'))
    return () => {
      current = false
    }
  }, [wantsOnboarding])

  // The wizard sits inside the locale provider too, so it reads in the person's
  // language and direction (Hebrew → RTL), and the shell keeps them after it.
  if (wantsOnboarding && serverSetup === 'needed') {
    return (
      <VentureProvider>
        <LocaleProvider>
          <OnboardingWizard onComplete={() => setShowOnboarding(false)} />
        </LocaleProvider>
      </VentureProvider>
    )
  }

  return (
    <VentureProvider>
      <LocaleProvider>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-[60] focus:top-4 focus:start-4 focus:px-4 focus:py-2 focus:rounded-lg focus:bg-brand-400 focus:text-black focus:text-sm focus:font-medium"
        >
          Skip to content
        </a>
        <div className="flex h-screen bg-background">
          <DesktopSidebar onSearch={() => setPaletteOpen(true)} />
          <div className="flex flex-1 flex-col overflow-hidden min-w-0">
            <MobileHeader
              onToggle={() => setMobileOpen(true)}
              onSearch={() => setPaletteOpen(true)}
            />
            <MobileSheet
              open={mobileOpen}
              onClose={() => setMobileOpen(false)}
              onSearch={() => setPaletteOpen(true)}
            />
            <main
              id="main-content"
              className="flex-1 overflow-y-auto px-4 py-6 sm:px-8 sm:py-8 [view-transition-name:rz-main]"
            >
              <ErrorBoundaryWithLocation>
                <Suspense fallback={<PageSkeleton />}>
                  <Routes>
                    <Route path="/" element={<OverviewPage />} />
                    <Route path="/chat" element={<ChatPage />} />
                    <Route path="/ventures" element={<VenturesListPage />} />
                    <Route path="/ventures/:key" element={<VentureDetailPage />} />
                    <Route path="/ventures/:key/agents/:id" element={<AgentDetailPage />} />
                    <Route path="/activity" element={<ActivityPage />} />
                    <Route path="/evolution" element={<EvolutionPage />} />
                    <Route path="/approvals" element={<ApprovalsPage />} />
                    <Route path="/skills" element={<SkillsPage />} />
                    <Route path="/tools" element={<ToolsPage />} />
                    <Route path="/pipelines" element={<PipelineBuilderPage />} />
                    <Route path="/workflows" element={<WorkflowEditorPage />} />
                    <Route path="/routing" element={<RoutingPage />} />
                    <Route path="/integrations" element={<IntegrationsPage />} />
                    <Route path="/setup" element={<SetupPage />} />
                    <Route path="/settings" element={<SettingsPage />} />
                    <Route path="/settings/agent-tokens" element={<AgentTokensPage />} />
                    <Route path="/docs" element={<DocsPage />} />
                    <Route path="/missions" element={<MissionsPage />} />
                    <Route path="/knowledge" element={<KnowledgeMapPage />} />
                    <Route path="/dreams" element={<DreamInboxPage />} />
                    <Route path="*" element={<NotFoundPage />} />
                  </Routes>
                </Suspense>
              </ErrorBoundaryWithLocation>
            </main>
          </div>
        </div>
        <ShellPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      </LocaleProvider>
    </VentureProvider>
  )
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageSkeleton />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        {/* Design system reference: static, no data, so it needs no sign-in */}
        <Route path="/design" element={<DesignPage />} />
        <Route
          path="*"
          element={
            <AuthGuard>
              <AuthenticatedShell />
            </AuthGuard>
          }
        />
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <TourProvider>
              <ErrorBoundary>
                <AppRoutes />
              </ErrorBoundary>
            </TourProvider>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </ThemeProvider>
  )
}
