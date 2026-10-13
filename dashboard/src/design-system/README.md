# Drawing Set — the RealizeOS design system (v2)

RealizeOS is the governed engine of a field practice: real-estate developers, architects and builders. Agents prepare things that touch money, contracts and people, and a person decides. Drawing Set is built around that moment, and it borrows its language from the drawing set those people read every day: blueprint graphite, drafting paper, hi-vis survey yellow, redlines, stamps, title blocks and leader lines.

**See it live:** open `/design` in the dashboard (no sign-in needed). Every token, component and motion on this page is the real code, shown on real product content in English and Hebrew, dark and light.

---

## Principles

1. **Colour is a word, not a coat of paint.** Yellow is the brand, or "held for you". Green is a decision made. Red is a redline. Blue is a source. Violet is an agent at work. Anything without a meaning is grey.
2. **Show the source.** A figure an agent produced links to the document it came from (`SourceRef`). A figure that failed a check is redlined.
3. **Calm by default, one loud moment.** Productive motion is quick and goes unnoticed. The stamp is the one expressive moment, and it plays only when a decision lands.
4. **Two languages, one voice.** Logical properties everywhere; every primitive is tested in RTL. IBM Plex has a real Hebrew cut, so the type does not change voice between languages.
5. **Keyboard first, not keyboard only.** Ctrl/⌘ K reaches every page and action. Every control has a visible focus state and an accessible name.
6. **The field's vocabulary.** Title blocks, sheet references, leader lines, stamps and redlines, not generic SaaS cards.

---

## Files

| File | What it holds |
| --- | --- |
| `tokens.css` | Colour (two modes), type, space, radius, elevation, layers, density. Every v1 `--rz-*` name still exists. |
| `motion.css` | Durations, easings, physics springs (CSS `linear()`), keyframes, the route view transition, reduced motion. |
| `fonts.css` | Base type rules. Families load once in `index.html`. |
| `effects.css` | `.fx-*` signature surfaces (glass, glow, grid, brand mark). Reserved for chrome and one hero per page. |
| `components.css` | Framework-free `.rz-*` primitives. React wrappers in `components/ui/` only compose these classes. |
| `tokens.json` | Style Dictionary export, **generated** by `python scripts/build_design_tokens.py`. Don't edit by hand. |
| `design-system.test.tsx` | Contrast for every text token in both modes, mirror-safe primitives, reduced motion. |
| `ILLUSTRATION.md` | Line-art language for empty states and diagrams. |

`src/index.css` is the Tailwind v4 bridge. It declares the cascade layer order first, imports the design system into `@layer components` (so utilities can still adjust any primitive, and Tailwind's preflight sits below it), and maps Tailwind names onto the tokens. That mapping includes the raw hues pages already use: `text-red-400` now means *danger*, `bg-emerald-400` means *success*, and so on, so old pages follow the system in light mode without being edited.

---

## Colour

| Role | Token | Night (dark) | Paper (light) |
| --- | --- | --- | --- |
| Page | `--rz-bg` | `#0e1218` | `#f4f5f2` |
| Panels | `--rz-bg-raised` | `#151a22` | `#ffffff` |
| Text | `--rz-fg` | `#e8ecf2` | `#17202b` |
| Brand · hi-vis | `--rz-accent` | `#ffcc00` | `#ffcc00` (fill only) |
| Brand as text | `--rz-accent-text` | `#ffd23f` | `#7a5c00` |
| Approved, done | `--rz-success` | `#3ccf8e` | `#13784a` |
| Needs attention | `--rz-warning` | `#ffa63d` | `#a35400` |
| Redline | `--rz-danger` | `#ff6b5c` | `#c4311f` |
| Source, link | `--rz-info` | `#6aa8ff` | `#1f56c3` |
| Agent activity | `--rz-agent` | `#b69cff` | `#6544d0` |

On paper the brand yellow is 1.4:1 against the page, so it is only ever a fill under ink: focus rings, text and borders switch to ink or `--rz-accent-text`. Every text pair passes WCAG AA (4.5:1), and placeholders pass 3:1; `design-system.test.tsx` enforces this.

## Type

IBM Plex Sans + IBM Plex Sans Hebrew, IBM Plex Mono for code and IDs, and Poppins only in the wordmark. Five sizes do almost all the product's work: 12 caption, 13 dense UI, 14 body, 16 reading, 18 panel title, plus 22 for page titles and 36 for key figures. Figures use tabular numbers.

## Motion

Two registers, after IBM Carbon:

| Register | Durations | Used for |
| --- | --- | --- |
| Productive | 80 · 140 · 220 · 360ms | Press, hover, menus, popovers, toasts, route change, sheets |
| Expressive | 300ms settle spring · 480ms bounce spring · 560ms | Tabs ink, switch knob, toasts arriving, **the stamp** |

Springs are generated from real physics (stiffness/damping) and shipped as CSS `linear()` with `cubic-bezier` fallbacks, so no animation library is needed. Rules: motion answers an action or reports a state change; enter slower than exit; travel 4–8px; only running work breathes (`StatusDot live`); and `prefers-reduced-motion` keeps fades while dropping all travel.

## Components

| Group | React (`components/ui/`) | Classes |
| --- | --- | --- |
| Actions | `Button` (primary, secondary, ghost, danger, approve; `busy`), `IconButton` | `.rz-btn`, `.rz-icon-btn` |
| Input | `Field`, `Switch` | `.rz-input`, `.rz-select`, `.rz-check`, `.rz-chip` |
| Navigation | `Tabs`, `Segmented` (spring indicator), `CommandPalette` (⌘K) | `.rz-tabs`, `.rz-segmented`, `.rz-palette` |
| Display | `Badge`, `StatusDot`, `Kbd`, `Panel`, `Stat` (counts up), `EmptyState`, `Skeleton` | `.rz-avatar`, `.rz-table`, `.rz-progress` |
| Overlays | `Dialog` (native `<dialog>`), `ConfirmDialog`, toasts (top-layer popover) | `.rz-menu`, `[data-tip]` tooltips |
| Field language | `TitleBlock`, `Stamp`, `Trail`, `SourceRef` | `.rz-held`, `.rz-redline`, `.rz-drafting-grid` |

## Using it

```tsx
import { Panel } from '@/components/ui/panel'
import { Button } from '@/components/ui/button'
import { Stamp } from '@/components/ui/stamp'

<Panel title="Payment request 14" held={!decided} footer={<Button variant="approve">Approve payment</Button>}>
  {decided && <Stamp decision="approved" by="Dana · 14:02" strike />}
</Panel>
```

Modes and density are root attributes: `<html data-mode="dark|light" data-density="compact|comfy">`.

## Market

What the leading products do well and what Drawing Set takes from each is in the "Market" section of `/design`: Linear, Vercel Geist, Stripe, IBM Carbon, Material 3 Expressive, the agent builders (n8n, Relevance AI, Lindy), LangSmith, and the AEC platforms (Procore, Autodesk Build).
