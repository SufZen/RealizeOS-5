import { access, mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

export const DEFAULT_VENTURE_KEY = "my-venture";
export const DEFAULT_VENTURE_NAME = "My Venture";

export const FABRIC_DIRS = [
  "F-foundations",
  "A-agents",
  "B-brain",
  "R-routines",
  "R-routines/skills",
  "I-insights",
  "C-creations",
];

const RESERVED_WINDOWS_NAMES = new Set([
  "con",
  "prn",
  "aux",
  "nul",
  "com1",
  "com2",
  "com3",
  "com4",
  "com5",
  "com6",
  "com7",
  "com8",
  "com9",
  "lpt1",
  "lpt2",
  "lpt3",
  "lpt4",
  "lpt5",
  "lpt6",
  "lpt7",
  "lpt8",
  "lpt9",
]);

const VENTURE_KEY_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

export function validateVentureKey(key: string): string {
  if (!VENTURE_KEY_PATTERN.test(key) || RESERVED_WINDOWS_NAMES.has(key)) {
    throw new Error(
      "Invalid venture key. Use a path-safe slug with lowercase letters, numbers, and hyphens, such as my-saas."
    );
  }
  return key;
}

function starterFiles(name: string): Record<string, string> {
  return {
    "F-foundations/venture-identity.md": `# Venture Identity

This file defines **your business** and guides how all AI agents represent it.

## Business Name & Tagline
${name} - [Your tagline here]

## Mission
[Your mission statement]

## Target Audience
- Primary: [Description]
- Secondary: [Description]

## Core Values
1. [Value 1]
2. [Value 2]
3. [Value 3]
`,
    "F-foundations/venture-voice.md": `# Venture Voice

## Tone
- Professional
- Clear
- Helpful

## Writing Rules
- Be specific.
- Match the audience.
- Keep recommendations actionable.
`,
    "A-agents/_README.md": `# Agents

This folder contains the venture's Markdown agent definitions.
`,
    "A-agents/orchestrator.md": `# Orchestrator Agent

## Role
General coordinator and planner.
`,
    "A-agents/writer.md": `# Writer Agent

## Role
Create clear, useful content for this venture.
`,
    "A-agents/reviewer.md": `# Reviewer Agent

## Role
Review content for quality, accuracy, and fit.
`,
    "A-agents/analyst.md": `# Analyst Agent

## Role
Research, compare, synthesize, and explain.
`,
    "B-brain/domain-knowledge.md": `# Domain Knowledge

Capture important facts, terminology, market notes, and context for this venture.
`,
    "B-brain/market-notes.md": `# Market Notes

Track customers, competitors, trends, and positioning.
`,
    "R-routines/state-map.md": `# State Map

## Active Priorities
- [Add current priorities]

## Open Loops
- [Add follow-ups]
`,
    "R-routines/skills/client-proposal.yaml": "name: client-proposal\ntrigger: proposal\npipeline: [analyst, writer, reviewer]\n",
    "R-routines/skills/content-pipeline.yaml": "name: content-pipeline\ntrigger: content\npipeline: [writer, reviewer]\n",
    "R-routines/skills/email-campaign.yaml": "name: email-campaign\ntrigger: email\npipeline: [writer, reviewer]\n",
    "R-routines/skills/research-workflow.yaml": "name: research-workflow\ntrigger: research\npipeline: [analyst, orchestrator]\n",
    "R-routines/skills/social-media.yaml": "name: social-media\ntrigger: social\npipeline: [writer, reviewer]\n",
    "R-routines/skills/weekly-review.yaml": "name: weekly-review\ntrigger: weekly review\npipeline: [analyst, orchestrator]\n",
    "I-insights/learning-log.md": "# Learning Log\n\nRecord durable lessons and decisions for this venture.\n",
    "C-creations/README.md": "# Creations\n\nDrafts, deliverables, and finished outputs live here.\n",
  };
}

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export async function writeVentureTemplate(
  projectDir: string,
  key: string,
  name: string,
  options: { overwrite?: boolean } = {}
): Promise<void> {
  validateVentureKey(key);
  const ventureDir = join(projectDir, "systems", key);

  for (const dir of FABRIC_DIRS) {
    await mkdir(join(ventureDir, dir), { recursive: true });
  }

  for (const [relativePath, content] of Object.entries(starterFiles(name))) {
    const path = join(ventureDir, relativePath);
    if (options.overwrite || !(await fileExists(path))) {
      await writeFile(path, content, "utf-8");
    }
  }
}
