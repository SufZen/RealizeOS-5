# @realizeos/design-system

The shared design substrate for the RealizeOS marketing site (`realizeos-site`) and the RealizeOS-5 product dashboard. Both apps consume the same CSS variables, the same fonts, and the same signature effects — so the product reads as the operator dashboard that lives behind the marketing site.

**Anchor:** every value here was lifted from `realizeos-site` and given a canonical name under the `--rz-*` namespace. The site barely changes; the product comes into line with it.

---

## What's in the box

| File | What it does | Where it imports from |
|---|---|---|
| `tokens.css` | All CSS variables — color, type scale, spacing, radius, motion. Light + dark. | `:root`, `[data-mode="dark"]`, `[data-mode="light"]` |
| `fonts.css`  | Google Fonts import: Poppins, Rubik (RTL), JetBrains Mono. Sets the `[dir="rtl"]` family swap. | `@import` from Google Fonts |
| `keyframes.css` | `fade-up`, `fade-in`, `popup-in`, `float`, `accordion-*`, etc., namespaced `rz-*`. | — |
| `effects.css` | `.fx-glass`, `.fx-glow`, `.fx-gradient-text`, `.fx-dot-grid`, `.fx-animated-border`, `.fx-illustration-glow`. | — |
| `components.css` | Class primitives: `.rz-btn`, `.rz-input`, `.rz-badge`, `.rz-card`, `.rz-code`, `.rz-status-dot`. | — |
| `index.css` | One-line import that pulls all of the above in order. | — |
| `tokens.json` | Machine-readable tokens (Style Dictionary-compatible) for native/iOS/Android consumers. | — |
| `site-tailwind.config.js` | Adapter for `realizeos-site` — keeps every legacy class name working, points each value at `--rz-*`. | — |
| `product-index.css` | Adapter for the RealizeOS-5 dashboard — replaces the current `dashboard/src/index.css`. | — |

---

## Install

In a pnpm/yarn workspace (recommended):

```bash
# from the monorepo root
pnpm add @realizeos/design-system --filter realizeos-site
pnpm add @realizeos/design-system --filter realize-os-dashboard
```

Or copy the files directly into each repo under `src/design-system/`.

---

## Use it in the site (`realizeos-site`)

```css
/* src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

@import "@realizeos/design-system/index.css";
```

Replace `tailwind.config.js` with `dist/site-tailwind.config.js` from this package. Every existing class (`bg-brand-yellow`, `text-brand-yellow-hover`, `bg-bg-elevated`, `bg-card-hover`, `text-text-secondary`, etc.) keeps working — it now resolves to a `var(--rz-*)`.

Drop the legacy effect rules from `src/index.css` (the `.glass`, `.glow-yellow`, `.text-gradient-yellow`, `.dot-grid`, `.animated-border` blocks). They now come from `@realizeos/design-system/effects.css` under `.fx-*` names — search/replace the usages.

```diff
- <nav className="glass fixed inset-x-0 …">
+ <nav className="fx-glass fixed inset-x-0 …">

- <span className="text-gradient-yellow text-glow-yellow">…</span>
+ <span className="fx-gradient-text">…</span>

- <Button className="glow-yellow">…</Button>
+ <Button className="fx-glow">…</Button>
```

---

## Use it in the product (`RealizeOS-5/dashboard`)

```css
/* dashboard/src/index.css — replace the file's contents with this */
@import "@realizeos/design-system/index.css";
@import "tailwindcss";

@theme {
  /* …adapter exports (already in dist/product-index.css) */
}
```

The full replacement file is `dist/product-index.css`. Every existing utility class in the dashboard (`bg-brand-400`, `bg-surface-700`, `text-foreground`, etc.) keeps working — they now resolve to the shared tokens.

Then swap the dark/light mode hook:

```diff
- // dashboard/src/components/theme-provider.tsx
- document.documentElement.classList.toggle('light', mode === 'light');
+ document.documentElement.setAttribute('data-mode', mode);
```

Add `data-density="compact"` on the dashboard's root element so dense product UI keeps its tighter rhythm:

```diff
- <body>
+ <body data-density="compact" data-mode="dark">
```

---

## Mode + density attributes

The system controls light/dark and density via root attributes — set once on `<html>` or `<body>`:

```html
<!-- Site (default) -->
<html data-mode="dark" data-density="comfy">

<!-- Product -->
<html data-mode="dark" data-density="compact">
```

A user-facing theme toggle just flips `data-mode` between `"dark"` and `"light"`.

---

## Migration guides

- `MIGRATION-site.md` — step-by-step for the marketing site repo (mostly a rename)
- `MIGRATION-product.md` — step-by-step for the product dashboard (the real lift)

---

## Token reference

See `tokens.json` for the machine-readable full list, or `tokens.css` for the human-readable CSS form. The full visual spec lives at `realizeos.ai/design` (also bundled in this repo as `index.html`).
