import { useState, lazy, Suspense, Component, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Briefcase,
  Activity,
  Sparkles,
  ShieldCheck,
  Settings,
  Bot,
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
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { ThemeProvider } from '@/components/theme-provider'
import { ThemeToggle } from '@/components/theme-toggle'
import { TourProvider } from '@/components/tour-provider'

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

import OnboardingWizard, { isOnboardingComplete } from '@/components/onboarding-wizard'

const navGroups = [
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
    label: 'Configure',
    items: [
      { to: '/tools', icon: Wrench, label: 'Tools' },
      { to: '/integrations', icon: Puzzle, label: 'Integrations' },
      { to: '/setup', icon: Plug, label: 'Setup' },
      { to: '/settings', icon: Settings, label: 'Settings' },
    ],
  },
]

function NavContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1 flex-1" data-tour="sidebar">
      {navGroups.map((group) => (
        <div key={group.label} className="mb-3">
          <span className="px-3 mb-1 block text-[10px] uppercase tracking-widest text-muted-foreground/60 font-semibold">
            {group.label}
          </span>
          {group.items.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={onNavigate}
              data-tour={`nav-${label.toLowerCase()}`}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                  isActive
                    ? 'bg-brand-400/10 text-brand-400 font-medium'
                    : 'text-muted-foreground hover:bg-surface-700 hover:text-foreground',
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  )
}

function Logo() {
  return (
    <div className="flex items-center gap-2 px-2 mb-8">
      <Bot className="h-8 w-8 text-brand-400" />
      <span className="text-xl font-bold text-foreground tracking-tight">RealizeOS</span>
    </div>
  )
}

function DesktopSidebar() {
  return (
    <aside className="hidden md:flex w-64 flex-col border-r border-border bg-surface-950 p-4">
      <Logo />
      <NavContent />
      <div className="mt-auto pt-4 border-t border-border" data-tour="theme-toggle">
        <ThemeToggle />
      </div>
    </aside>
  )
}

function MobileHeader({ onToggle }: { onToggle: () => void }) {
  return (
    <header className="flex md:hidden items-center justify-between border-b border-border bg-surface-950 px-4 py-3">
      <div className="flex items-center gap-2">
        <Bot className="h-6 w-6 text-brand-400" />
        <span className="text-lg font-bold text-foreground">RealizeOS</span>
      </div>
      <button
        onClick={onToggle}
        className="rounded-lg p-2 text-muted-foreground hover:bg-surface-700 hover:text-foreground transition-colors"
        aria-label="Toggle navigation"
      >
        <Menu className="h-5 w-5" />
      </button>
    </header>
  )
}

function MobileSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/60" onClick={onClose} />
      <div className="fixed inset-y-0 left-0 z-50 w-72 bg-surface-950 border-r border-border p-4 shadow-xl">
        <div className="flex items-center justify-between mb-6">
          <Logo />
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-muted-foreground hover:text-foreground"
            aria-label="Close navigation"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <NavContent onNavigate={onClose} />
      </div>
    </>
  )
}


class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { hasError: boolean; error: string }> {
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
            <div className="text-4xl mb-4">:(</div>
            <h2 className="text-xl font-bold text-foreground mb-2">Something went wrong</h2>
            <p className="text-sm text-muted-foreground mb-4">{this.state.error || 'An unexpected error occurred.'}</p>
            <div className="flex gap-3 justify-center">
              <button
                onClick={() => this.setState({ hasError: false, error: '' })}
                className="px-4 py-2 text-sm rounded-lg bg-brand-400 text-black hover:bg-brand-400/90 font-medium"
              >
                Retry
              </button>
              <button
                onClick={() => window.location.reload()}
                className="px-4 py-2 text-sm rounded-lg border border-border text-foreground hover:bg-surface-700 font-medium"
              >
                Reload Page
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

export default function App() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(!isOnboardingComplete())

  if (showOnboarding) {
    return (
      <ThemeProvider>
        <OnboardingWizard onComplete={() => setShowOnboarding(false)} />
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider>
      <BrowserRouter>
        <TourProvider>
        <div className="flex h-screen bg-background">
          <DesktopSidebar />
          <div className="flex flex-1 flex-col overflow-hidden">
            <MobileHeader onToggle={() => setMobileOpen(true)} />
            <MobileSheet open={mobileOpen} onClose={() => setMobileOpen(false)} />
            <main className="flex-1 overflow-y-auto p-6">
              <ErrorBoundaryWithLocation>
              <Suspense
                fallback={<div className="flex items-center justify-center h-64 text-muted-foreground">Loading...</div>}
              >
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
                </Routes>
              </Suspense>
              </ErrorBoundaryWithLocation>
            </main>
          </div>
        </div>
        </TourProvider>
      </BrowserRouter>
    </ThemeProvider>
  )
}
