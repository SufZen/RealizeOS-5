import { useState } from 'react';
import { BookOpen, ChevronRight, Search, ExternalLink, Zap, Shield, Brain, Wrench, Monitor, Rocket, Layers, Settings2, Cloud } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DocSection {
  id: string;
  title: string;
  icon: React.ReactNode;
  content: React.ReactNode;
}

export default function DocsPage() {
  const [activeSection, setActiveSection] = useState('overview');
  const [searchQuery, setSearchQuery] = useState('');

  const sections: DocSection[] = [
    {
      id: 'overview',
      title: 'Overview',
      icon: <Rocket className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <div>
            <h2 className="text-2xl font-bold text-foreground mb-3">Welcome to RealizeOS V5</h2>
            <p className="text-muted-foreground leading-relaxed">
              RealizeOS is an advanced, self-evolving AI Operations System built for absolute control, privacy, and performance.
              It coordinates AI agent teams, routes requests across multiple LLMs, and maintains a structured knowledge base that grows with your business.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { icon: '📡', title: 'Channel Layer', desc: 'API · Telegram · Dashboard · CLI' },
              { icon: '⚙️', title: 'Processing Engine', desc: 'Message pipeline · Routing · Sessions' },
              { icon: '🧠', title: 'Intelligence Layer', desc: 'Agents · Skills · LLM Router · Prompt Assembly' },
              { icon: '🔧', title: 'Tools & Extensions', desc: '24 Google tools · Web · Browser · MCP' },
              { icon: '🏗️', title: 'Infrastructure', desc: 'Storage · KB Search · Evolution · Optimization' },
              { icon: '🔒', title: 'Security', desc: 'JWT · RBAC · Injection Defense · Audit' },
            ].map(item => (
              <div key={item.title} className="bg-card border border-border rounded-xl p-4 hover:border-brand-400/30 transition-colors">
                <div className="text-2xl mb-2">{item.icon}</div>
                <h4 className="text-foreground font-semibold text-sm">{item.title}</h4>
                <p className="text-muted-foreground text-xs mt-1">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      id: 'getting-started',
      title: 'Getting Started',
      icon: <Zap className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">Getting Started</h2>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">Prerequisites</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Requirement</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Version</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Python', '3.11+', 'Required'],
                    ['LLM API key', '—', 'At least one: Anthropic, Google, OpenAI, or Ollama'],
                    ['Docker', '24.0+', 'Optional (containerized deployment)'],
                  ].map(([req, ver, note]) => (
                    <tr key={req} className="border-b border-border">
                      <td className="py-2 px-3 text-foreground font-medium">{req}</td>
                      <td className="py-2 px-3 text-muted-foreground">{ver}</td>
                      <td className="py-2 px-3 text-muted-foreground">{note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">Installation</h3>
            <pre className="bg-surface-800 border border-border rounded-lg p-4 text-sm text-muted-foreground overflow-x-auto">
{`# Option A: One-click installer (Windows)
# Download and run Install-RealizeOS.bat

# Option B: Manual setup
git clone https://github.com/SufZen/RealizeOS-5.git
cd RealizeOS-5
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add your API keys
python cli.py serve`}
            </pre>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">FABRIC Knowledge Structure</h3>
            <p className="text-muted-foreground mb-3">Every venture's knowledge base follows the FABRIC directory structure:</p>
            <div className="grid grid-cols-1 gap-2">
              {[
                ['F-foundations/', 'Venture identity, voice rules', 'identity.md, voice-guide.md'],
                ['A-agents/', 'Agent team definitions', 'writer.md, analyst.md'],
                ['B-brain/', 'Domain knowledge, research', 'market-data.md, competitors.md'],
                ['R-routines/', 'Skills, workflows, SOPs', 'skills/content-pipeline.yaml'],
                ['I-insights/', 'Memory, learning log', 'learning-log.md, feedback.md'],
                ['C-creations/', 'Deliverables, outputs', 'drafts/, final/'],
              ].map(([dir, purpose, files]) => (
                <div key={dir} className="flex items-start gap-3 bg-card border border-border rounded-lg p-3">
                  <code className="text-brand-400 text-sm font-mono whitespace-nowrap">{dir}</code>
                  <div>
                    <span className="text-foreground text-sm">{purpose}</span>
                    <span className="text-muted-foreground text-xs ml-2">({files})</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'dashboard',
      title: 'Dashboard Features',
      icon: <Monitor className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">Dashboard Features</h2>
          <p className="text-muted-foreground">The dashboard provides a visual interface for managing your RealizeOS system.</p>
          <div className="space-y-4">
            {[
              { title: 'Overview', desc: 'System-wide summary: venture count, agent status, errors, and recent activity at a glance.' },
              { title: 'Chat', desc: 'Interactive AI chat interface. Select your venture and agent, then converse directly.' },
              { title: 'Ventures', desc: 'Manage your businesses/projects. Each venture has its own FABRIC knowledge structure.' },
              { title: 'Skills', desc: 'View and manage YAML-defined workflows that chain agents and tools.' },
              { title: 'Pipelines', desc: 'Visual workflow builder for creating multi-step agent pipelines.' },
              { title: 'Activity', desc: 'Real-time SSE-powered feed of all system events.' },
              { title: 'Settings', desc: 'Feature flags, LLM providers, storage config, and system maintenance.' },
            ].map(item => (
              <div key={item.title} className="bg-card border border-border rounded-lg p-4">
                <h4 className="text-foreground font-semibold text-sm mb-1">{item.title}</h4>
                <p className="text-muted-foreground text-xs">{item.desc}</p>
              </div>
            ))}
          </div>
          <div className="bg-surface-800 border border-border rounded-lg p-4">
            <h3 className="text-foreground font-semibold mb-2">🎨 Theme Toggle</h3>
            <p className="text-muted-foreground text-sm">Switch between Dark, Light, and System themes using the toggle at the bottom of the sidebar.</p>
          </div>
          <div className="bg-surface-800 border border-border rounded-lg p-4">
            <h3 className="text-foreground font-semibold mb-2">🎯 Guided Tour</h3>
            <p className="text-muted-foreground text-sm">A 15-step interactive tour auto-starts on your first visit. Restart it anytime from Settings → Help & Support.</p>
          </div>
        </div>
      ),
    },
    {
      id: 'agents',
      title: 'Agents & Intelligence',
      icon: <Brain className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">Agents & Intelligence Layer</h2>
          <p className="text-muted-foreground">Agents are specialized AI team members with unique roles and capabilities.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { icon: '🎯', name: 'Orchestrator', desc: 'General coordinator, task router, and planner.' },
              { icon: '✍️', name: 'Writer', desc: 'Content creation — blog posts, emails, social media.' },
              { icon: '🔍', name: 'Reviewer', desc: 'Quality gatekeeper with scoring framework.' },
              { icon: '📊', name: 'Analyst', desc: 'Research, strategy, competitive analysis.' },
            ].map(a => (
              <div key={a.name} className="bg-card border border-border rounded-xl p-4">
                <div className="text-xl mb-2">{a.icon}</div>
                <h4 className="text-foreground font-semibold text-sm">{a.name}</h4>
                <p className="text-muted-foreground text-xs mt-1">{a.desc}</p>
              </div>
            ))}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">Multi-LLM Routing</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Task Class</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Default Model</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Use Case</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Simple', 'Gemini Flash', 'Quick lookups, formatting'],
                    ['Content', 'Claude Sonnet', 'Writing, analysis'],
                    ['Complex', 'Claude Opus', 'Strategy, multi-step reasoning'],
                  ].map(([cls, model, use]) => (
                    <tr key={cls} className="border-b border-border">
                      <td className="py-2 px-3 text-brand-400 font-medium">{cls}</td>
                      <td className="py-2 px-3 text-foreground">{model}</td>
                      <td className="py-2 px-3 text-muted-foreground">{use}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: 'tools',
      title: 'Tools & Extensions',
      icon: <Wrench className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">Tools & Extensions</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 text-muted-foreground font-medium">Service</th>
                  <th className="text-left py-2 px-3 text-muted-foreground font-medium">Tools</th>
                  <th className="text-left py-2 px-3 text-muted-foreground font-medium">Capabilities</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ['📧 Gmail', '8', 'Search, read, send, draft, reply, forward, triage, label'],
                  ['📅 Calendar', '4', 'List events, create, update, find free time'],
                  ['📁 Drive', '9', 'Search, list, read, create doc, append, upload, download'],
                  ['📊 Sheets', '3', 'Read, append, create'],
                  ['🔍 Web Search', '1', 'Brave API powered web search'],
                  ['🌐 Browser', '1', 'Headless Chromium page interaction'],
                ].map(([svc, count, caps]) => (
                  <tr key={svc} className="border-b border-border">
                    <td className="py-2 px-3 text-foreground font-medium">{svc}</td>
                    <td className="py-2 px-3 text-brand-400">{count}</td>
                    <td className="py-2 px-3 text-muted-foreground">{caps}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ),
    },
    {
      id: 'storage',
      title: 'Storage & Backup',
      icon: <Cloud className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">Storage & Backup</h2>
          <p className="text-muted-foreground">RealizeOS uses a pluggable storage system. Local filesystem is the default, with S3-compatible cloud storage for cross-device sync.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { icon: '💾', title: 'Local Storage', desc: 'Default. Filesystem-based with atomic writes.' },
              { icon: '☁️', title: 'S3-Compatible', desc: 'AWS S3, MinIO, DigitalOcean Spaces, Backblaze B2, Cloudflare R2.' },
            ].map(s => (
              <div key={s.title} className="bg-card border border-border rounded-xl p-4">
                <div className="text-2xl mb-2">{s.icon}</div>
                <h4 className="text-foreground font-semibold text-sm">{s.title}</h4>
                <p className="text-muted-foreground text-xs mt-1">{s.desc}</p>
              </div>
            ))}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">Configure Cloud Storage</h3>
            <p className="text-muted-foreground text-sm mb-2">Go to <strong className="text-foreground">Settings → Storage & Backup</strong> to:</p>
            <ul className="list-disc list-inside text-muted-foreground text-sm space-y-1">
              <li>Enter your S3 bucket, region, and credentials</li>
              <li>Test connection before saving</li>
              <li>Enable automatic bi-directional sync</li>
              <li>Export / import data as zip</li>
            </ul>
          </div>
        </div>
      ),
    },
    {
      id: 'security',
      title: 'Security',
      icon: <Shield className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">Security</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { title: 'JWT Authentication', desc: 'Token-based API access with configurable expiration and refresh flow.' },
              { title: 'RBAC', desc: 'Role-based access control defined in YAML (admin, operator, viewer).' },
              { title: 'Injection Defense', desc: 'Multi-layer prompt injection detection with pattern scanning and threat scoring.' },
              { title: 'Audit Logging', desc: 'Every security-relevant action logged to SQLite.' },
            ].map(s => (
              <div key={s.title} className="bg-card border border-border rounded-lg p-4">
                <h4 className="text-foreground font-semibold text-sm mb-1">{s.title}</h4>
                <p className="text-muted-foreground text-xs">{s.desc}</p>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      id: 'updating',
      title: 'Updating & Migration',
      icon: <Layers className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">Updating & Migration</h2>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">🔄 Updating RealizeOS</h3>
            <p className="text-muted-foreground text-sm mb-2">Run <code className="bg-surface-800 px-2 py-0.5 rounded text-brand-400 text-xs">Update-RealizeOS.bat</code> from your installation folder. It will:</p>
            <ol className="list-decimal list-inside text-muted-foreground text-sm space-y-1">
              <li>Check GitHub Releases for the latest version</li>
              <li>Back up your data (.env, FABRIC files, databases, credentials)</li>
              <li>Download and install the update</li>
              <li>Restore your data automatically</li>
              <li>Roll back if anything fails</li>
            </ol>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">📦 Migrating Data</h3>
            <p className="text-muted-foreground text-sm mb-2">Run <code className="bg-surface-800 px-2 py-0.5 rounded text-brand-400 text-xs">Migrate-RealizeOS.bat</code> to transfer data from another installation:</p>
            <ul className="list-disc list-inside text-muted-foreground text-sm space-y-1">
              <li>Point it to your old RealizeOS folder</li>
              <li>It scans for FABRIC data, config, databases, and credentials</li>
              <li>Choose conflict resolution: skip, overwrite, or ask-per-file</li>
              <li>Automatically rebuilds the KB index after migration</li>
            </ul>
          </div>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">🗑️ Uninstalling</h3>
            <p className="text-muted-foreground text-sm mb-2">Run <code className="bg-surface-800 px-2 py-0.5 rounded text-brand-400 text-xs">Uninstall-RealizeOS.bat</code>. You can choose to:</p>
            <ul className="list-disc list-inside text-muted-foreground text-sm space-y-1">
              <li><strong className="text-foreground">Keep data</strong> — backs up FABRIC files, .env, databases to ~/RealizeOS-Backup</li>
              <li><strong className="text-foreground">Delete everything</strong> — complete removal, nothing left behind</li>
            </ul>
          </div>
        </div>
      ),
    },
    {
      id: 'cli',
      title: 'CLI Reference',
      icon: <Settings2 className="w-4 h-4" />,
      content: (
        <div className="space-y-6">
          <h2 className="text-2xl font-bold text-foreground">CLI Reference</h2>
          <pre className="bg-surface-800 border border-border rounded-lg p-4 text-sm text-muted-foreground overflow-x-auto">
{`python cli.py init --template NAME           # Initialize from template
python cli.py serve [--port PORT] [--reload] # Start API + dashboard
python cli.py bot                            # Start Telegram bot
python cli.py status                         # Show system status
python cli.py index                          # Rebuild KB search index
python cli.py venture create --key KEY       # Create new venture
python cli.py venture delete --key KEY       # Delete venture
python cli.py venture list                   # List all ventures
python cli.py setup-google                   # Run Google OAuth flow`}
          </pre>
          <div>
            <h3 className="text-lg font-semibold text-foreground mb-3">API Endpoints</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Method</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Endpoint</th>
                    <th className="text-left py-2 px-3 text-muted-foreground font-medium">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['POST', '/api/chat', 'Send message, get AI response'],
                    ['GET', '/api/systems', 'List all configured systems'],
                    ['GET', '/api/storage/config', 'Get storage configuration'],
                    ['PUT', '/api/storage/config', 'Update storage settings'],
                    ['POST', '/api/storage/test', 'Test S3 connection'],
                    ['POST', '/api/storage/export', 'Export all user data'],
                    ['GET', '/health', 'Health check'],
                    ['GET', '/status', 'Detailed system status'],
                  ].map(([method, endpoint, desc]) => (
                    <tr key={endpoint} className="border-b border-border">
                      <td className="py-2 px-3"><span className={`text-xs font-bold ${method === 'POST' || method === 'PUT' ? 'text-brand-400' : 'text-purple-400'}`}>{method}</span></td>
                      <td className="py-2 px-3 text-foreground font-mono text-xs">{endpoint}</td>
                      <td className="py-2 px-3 text-muted-foreground">{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ),
    },
  ];

  const filteredSections = searchQuery
    ? sections.filter(s => s.title.toLowerCase().includes(searchQuery.toLowerCase()))
    : sections;

  const activeContent = sections.find(s => s.id === activeSection);

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <div className="w-56 shrink-0 border-r border-border p-4 space-y-1 overflow-y-auto">
        <div className="flex items-center gap-2 mb-4">
          <BookOpen className="w-5 h-5 text-brand-400" />
          <h3 className="text-foreground font-semibold text-sm">Documentation</h3>
        </div>
        <div className="relative mb-3">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search docs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-surface-800 border border-border rounded-lg py-1.5 pl-8 pr-3 text-xs text-foreground placeholder:text-muted-foreground outline-none focus:border-brand-400 focus:ring-1 focus:ring-brand-400"
          />
        </div>
        {filteredSections.map(section => (
          <button
            key={section.id}
            onClick={() => { setActiveSection(section.id); setSearchQuery(''); }}
            className={cn(
              'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors',
              activeSection === section.id
                ? 'bg-brand-400/10 text-brand-400 font-medium'
                : 'text-muted-foreground hover:text-foreground hover:bg-surface-700',
            )}
          >
            {section.icon}
            <span>{section.title}</span>
            {activeSection === section.id && <ChevronRight className="w-3 h-3 ml-auto" />}
          </button>
        ))}
        <div className="pt-4 mt-4 border-t border-border">
          <a
            href="/docs/user-guide.html"
            target="_blank"
            rel="noopener"
            className="flex items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Full Standalone Guide</span>
          </a>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8 max-w-3xl">
        {activeContent?.content}
      </div>
    </div>
  );
}
