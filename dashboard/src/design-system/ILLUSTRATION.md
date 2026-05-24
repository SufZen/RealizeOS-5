# Illustration & motion language

The site's existing `src/components/illustrations/` library — 35 SVG illustrations in line-art amber on dark — is the visual signature of RealizeOS. This doc defines how to *use* what's there consistently across the site, and how to *extend* it into the product (which currently ships zero illustrations).

---

## Style DNA — three rules

### 1 · Line over fill
Stroke is the figure, fill is the ghost. All shapes use amber strokes (1–1.5px). Fills are reserved for tinted, semi-transparent backgrounds (8–15% opacity). **Never** solid yellow blocks, gradient illustrations, or raster.

```svg
<!-- ✓ stroke only -->
<rect fill="none" stroke="#ffcc00" stroke-width="1.2" />

<!-- ✓ tinted fill + stroke -->
<rect fill="rgba(255,204,0,0.10)" stroke="#ffcc00" stroke-opacity="0.55" stroke-width="1.2" />

<!-- ✗ solid fill -->
<rect fill="#ffcc00" />
```

### 2 · Opacity does the layering
One color (`#ffcc00`), nine ranks. Never multiple hues inside an illustration. The ramp:

| Rank | Opacity | Use |
|---|---|---|
| 1 | 0.60 | Foreground glyph |
| 2 | 0.50 | Active node fill |
| 3 | 0.40 | Connector pulse |
| 4 | 0.30 | Resting node |
| 5 | 0.25 | Dashed connector |
| 6 | 0.20 | Spine / scaffold |
| 7 | 0.15 | Background frame |
| 8 | 0.12 | Far background |
| 9 | 0.08 | Tinted fill / halo edge |

### 3 · Geometry + mono type
Hexagons, circles, rounded rects (rx 4–8), dashed connectors (`stroke-dasharray="3 3"` or `"4 4"`), polylines. Labels in JetBrains Mono for codes/letters (8–14px), Poppins for word labels (9–11px). **No** characters, metaphor pictures, or scenery — every piece reads as a schematic of the actual product.

---

## Five tiers · what gets drawn at what size

| Tier | viewBox | Max width | Stroke | Density | Examples |
|---|---|---|---|---|---|
| **Hero** | 400×360 | 400px | 1.5px | High (~30 shapes) | `HeroAgentNetwork` |
| **Diagram** | 320×420 | 320px | 1–1.5px | High, labeled | `FabricDiagram`, `ProductMockup` |
| **Feature** | ~240×160 | 240px | 1–1.2px | Medium (~10 shapes) | All `Feature*`, `Pain*`, `UseCase*` |
| **Step** | 96×96 | 96px | 1.2px | Low (~4 shapes) | All `Step*Icon` |
| **Spot** | 48×48 | 48–64px | 1.2px | Very low (1–3 shapes) | New — for UI accents |
| **Empty** | 200×140 | 220px | 1.2px | Medium | New — for product zero-states |

---

## Placement & hierarchy rules

1. **One hero per page** — `HeroAgentNetwork`-class illustrations appear once. Site homepage, product `/onboarding` welcome. Never two on the same scroll.
2. **One diagram per section** — FABRIC, ProductMockup. Use when the layout is the message; skip if a short text block tells the same story.
3. **Features 1:1 with cards** — every feature card gets exactly one illustration drawn for that feature. Don't reuse; drawing a new one signals importance.
4. **Steps in linear groups** — Step icons live in 3–6 item rows connected by `StepConnector`. Each numbered. Animate sequentially with `staggerContainer`.
5. **Spots are punctuation** — 48px spot icons ride next to body copy in feature lists, badges, toolbars. Limit: one per row, never decorate every list item.
6. **Empty states earn illustration** — zero-state screens in the product get one Empty-tier illustration. Loaded pages don't.
7. **No illustration on dense UI** — data tables, log viewers, pipeline graph canvas — no decorative SVG. The data is the picture.
8. **Light-mode tonal shift** — replace `stroke="#ffcc00"` with `stroke="#cc9900"` in light mode (already the convention: `amber-500` dark → `amber-600` light).

---

## Motion vocabulary

The existing `src/components/illustrations/animation-variants.ts` already exports everything needed. The unification adds **one** new variant (`signalVariants`) — no other motion primitives.

| Variant | When to use | Tiers |
|---|---|---|
| `drawVariants` | Entry · once on viewport intersect (SVG path reveal) | Hero, Diagram, Feature |
| `staggerContainer(0.1)` + `fadeInChild` | Entry · grouped children | Hero satellites, FABRIC nodes, Steps |
| `floatVariants` (4s) | Continuous · idle motion | Hero, Diagram only |
| `floatSlowVariants` (6s) | Continuous · slower idle | Decorative orbiting elements |
| `pulseVariants` (3s) | Continuous · attention dot | Junction dots, signal indicators, "agent thinking" state |
| `orbitVariants(25)` | Continuous · slow rotate | Hero outer orbit ring only |
| **NEW** `signalVariants(from, to)` | Continuous · routed signal | Chat → agent, agent → tool, pipeline node → node |
| `shouldReduceMotion()` | Gate · always check before continuous variants | All |

Every continuous animation **must** check `shouldReduceMotion()` and short-circuit if true.

---

## Site · tighten what's there (Phase 1)

The site already has the assets. Today they ship some inconsistencies:

- [ ] **Standardize stroke weights** — currently 1, 1.2, 1.5 mixed inside the same files.
- [ ] **Replace inline Tailwind classes** (`stroke-amber-500/60`) with `var(--rz-accent)` + `stroke-opacity` so light mode auto-shifts.
- [ ] **Wrap every illustration** in `<motion.svg willChange="transform">` + add a `shouldReduceMotion()` gate to any continuous animation.
- [ ] **Pull labels** (Poppins / JBM) into a single text-style helper so font weights stay consistent.
- [ ] **Add `role="img"` + `aria-label`** to every illustration (some have it, some don't).

---

## Product · build out (Phase 2)

The product dashboard currently ships zero illustrations. The plan, prioritized:

### High value · ship first
- **Onboarding hero** — reuse `HeroAgentNetwork` on the welcome step.
- **5 Empty states** — at `/ventures`, `/chat`, `/approvals`, `/activity`, KB browser. Custom glyphs (sprout, mailbox, gate, compass, open book).
- **6 Setup wizard step icons** — same `StepIcon` style as the site, custom glyphs per step.

### Medium value
- **Agent portraits × 6+** — Sales / Research / QA / Ops / Brain / Critic. Hex frame + glyph inside + amber stroke ring.
- **Status illustrations × 3** — "thinking" (animated pulse hex), "routing" (signal traveling between nodes), "approved" (checkmark with halo).
- **Pipeline node icons** — replace plain Lucide icons on the pipeline-builder canvas with 32px spot illustrations.

### Where they go, page by page

| Surface | Page · component | Add | Tier |
|---|---|---|---|
| Site | Hero | (keep) `HeroAgentNetwork` — opacity tokens | Hero |
| Site | FAQ — empty answer | Spot · question-mark hex | Spot |
| Site | Use-case selector tabs | Static thumbnails from `UseCase*` at 48px | Spot |
| Product | `/onboarding` step 0 welcome | `HeroAgentNetwork` @ 320px | Hero |
| Product | `/onboarding` steps 1–6 | New StepIcon set (6 illustrations) | Step |
| Product | `/ventures` (empty) | New Empty · sprout | Empty |
| Product | `/chat` (empty) | New Empty · mailbox | Empty |
| Product | `/approvals` (empty) | New Empty · gate | Empty |
| Product | `/activity` (empty) | New Empty · compass | Empty |
| Product | KB browser (empty folder) | New Empty · open book | Empty |
| Product | Agent rows · sidebar | New AgentPortrait set | Spot |
| Product | Chat msg · agent "thinking" | Animated pulse-hex (inline) — `pulseVariants` | Spot |
| Product | Pipeline node icons | Replace Lucide with 32×32 spots | Spot |
| Product | Setup complete celebration | FABRIC diagram, animated draw-in | Diagram |
| Both | 404 page | Spot · compass + FABRIC node grid | Spot |
| Both | Error state | Spot · shield-X · amber stroke | Spot |

---

## GIFs & Lottie — sparing

- **Default to Framer Motion + SVG.** That's already the site's pattern; keep it.
- **Allowed Lottie use:**
  - GitHub README header — animated FABRIC, target < 100kb
  - Product onboarding "success" celebration after install
- **If a GIF is genuinely needed** (e.g. social share preview), export from the same SVG illustration:
  - 800px wide, 24 fps, < 800kb
  - Loop seamlessly · no jarring restart
- **Never use** stock 3D / kawaii / corporate-memphis GIFs. Doesn't match the line-art DNA — looks like a different product immediately.

---

## Drawing checklist · use for every new illustration

1. **Pick the tier first** (Hero / Diagram / Feature / Step / Empty / Spot). Locks viewBox, max-width, stroke weight.
2. **Sketch with primitives only:** `circle`, `rect` (rx 4–8), `polygon` (hex), `line` (solid + dashed 3 3 or 4 4), `polyline`. No path curves unless drawing a connector.
3. **One color:** `#ffcc00`. Vary only opacity — pick from the 9-step ramp.
4. **Add a single radial halo** behind Hero, Diagram, Empty tiers. Never on Feature, Step, Spot.
5. **Labels** (if any) in JetBrains Mono 8–14px for codes/letters, Poppins 9–11px for words.
6. **Wrap in motion:**
   ```jsx
   <motion.svg
     variants={staggerContainer(0.1)}
     initial="hidden"
     whileInView="visible"
     viewport={{ once: true }}
     role="img"
     aria-label="…"
   />
   ```
7. **Connectors animate** with `drawVariants`, nodes with `fadeInChild`.
8. **Continuous motion** (pulse / float / orbit) must be gated on `!shouldReduceMotion()`.
9. **Export** from `src/components/illustrations/index.ts`.
10. **Visual review** against the existing 35-illustration gallery — does the new one feel like it was drawn by the same hand?

---

## File layout · where it lives

```
packages/@realizeos/design-system/
└── illustrations/
    ├── index.ts                 # barrel export
    ├── animation-variants.ts    # motion primitives (existing, extended)
    │
    ├── hero/
    │   └── HeroAgentNetwork.tsx
    ├── diagram/
    │   ├── FabricDiagram.tsx
    │   └── ProductMockup.tsx
    ├── feature/                  # 8 existing feature illustrations
    ├── pain/                     # 3 existing
    ├── use-case/                 # 5 existing
    ├── step/                     # 6 existing + 6 new (product onboarding)
    ├── tier/                     # 5 existing
    ├── empty/                    # 5 NEW (product zero-states)
    ├── portrait/                 # 6 NEW (agent archetypes)
    ├── spot/                     # NEW (~12 inline UI icons)
    └── status/                   # 3 NEW (thinking · routing · approved)
```

Both the site and the product import from the same package:

```ts
import { HeroAgentNetwork, EmptyVentures, AgentPortraitSales } from '@realizeos/design-system/illustrations';
```
