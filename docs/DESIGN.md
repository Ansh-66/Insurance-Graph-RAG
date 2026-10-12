# DESIGN.md — House Style

> Single source of truth for visual style across **Claude Design**, **Google Stitch**, and **Claude Code**.
> Scope: **desktop-first websites** (responsive down to mobile as a quality floor, not the primary target).
> Rule for every consumer: **use only the values defined here. Never invent values or fall back to framework defaults.**

---

## 0. Anti-slop — banned patterns (read first)

These make a design read as AI-generated. Do not produce them under any circumstance.

- **No gradient accents as a crutch** — no gradient buttons, no gradient hero backgrounds, no `background-clip: text` gradient headlines, no mesh/blob gradients.
- **No glassmorphism / frosted-glass / backdrop-blur** panels.
- **No shadows as decoration.** Shadows only on true overlays (modal, dropdown, popover). Never on buttons or cards.
- **No emoji as icons or in headings.**
- **No oversized rounded corners.** Radius stays in the scale below; nothing looks like a bubble.
- **No icon-in-a-colored-circle feature grids** (the "hero → 3 pastel feature cards → CTA" template).
- **No decorative numbering** (01 / 02 / 03) unless the content is a genuine ordered sequence.
- **No default framework tokens** — not Tailwind's default `indigo-500`, `shadow-lg`, or unmodified ramps.
- **Avoid these three AI-cliché looks specifically:**
  1. Warm cream background (~`#F4F1EA`) + high-contrast serif + terracotta accent (~`#D97757`).
  2. Near-black background + one acid-green or vermilion accent.
  3. Broadsheet hairline-rule layout with zero radius and dense newspaper columns.
- **No timid centered everything.** Center is a deliberate choice, not a default. Use real left-aligned structure and intentional asymmetry.
- **No filler copy** — no "Elevate your workflow," "Unlock the power of," "Seamlessly." Write plain, specific, active-voice text.

Positive test: does the page have a clear typographic hierarchy, a felt grid, and exactly one memorable element? If not, it's slop regardless of how clean it looks.

---

## 1. Design principles

- **Restraint over decoration.** Whitespace and hierarchy do the work.
- **Spend boldness in one place.** One signature element per page; everything else stays quiet.
- **Type carries the personality**, not color or effects.
- **Structure encodes meaning.** Labels, dividers, and eyebrows describe real content, never decorate.
- **Content-first.** Chrome recedes; the words and data lead.

Voice/vibe: *clean, modern, quietly premium — a focused product, not a marketing splash.*

---

## 2. Color

Near-monochrome neutral base + **one** deliberate accent. Exact hex only.

> The accent below is a placeholder deep-blue chosen to avoid framework defaults. **Set one accent per brand.** Never introduce a second accent.

### Light theme
- `--bg`            `#FFFFFF`
- `--surface`       `#F6F7F9`  — cards, panels
- `--surface-alt`   `#ECEEF2`  — nested / hover surfaces
- `--border`        `#DFE2E8`  — hairlines, dividers, input outlines
- `--text`          `#14161B`  — primary (never pure #000000)
- `--text-muted`    `#565D6B`  — secondary, captions
- `--text-faint`    `#878E9B`  — placeholders, disabled
- `--accent`        `#1946C0`  — links, primary actions, focus
- `--accent-hover`  `#143A9E`
- `--accent-weak`   `#EDF1FC`  — accent-tinted backgrounds
- `--success`       `#0F8A54`
- `--warning`       `#B4690E`
- `--danger`        `#C4291F`

### Dark theme
- `--bg`            `#0D0F13`
- `--surface`       `#15181E`
- `--surface-alt`   `#1D212A`
- `--border`        `#282E38`
- `--text`          `#F1F3F7`
- `--text-muted`    `#9AA1AE`
- `--text-faint`    `#656C79`
- `--accent`        `#5B82F5`
- `--accent-hover`  `#7699F7`
- `--accent-weak`   `#151C33`
- `--success`       `#33BE7C`
- `--warning`       `#E0A048`
- `--danger`        `#E56A61`

Usage: `--accent` appears on ~one element per view. Status colors signal state only.

---

## 3. Typography

Personality lives here. Pair a **display** face with a **body** face — do not set everything in one family.

- **Display (headings):** a face with real character. Default: `Fraunces` (serif) *or* `Inter Tight` (if the brand is more technical). **This is the main per-brand personality lever — swap it deliberately.**
- **Body:** `Inter`, system-ui fallback.
- **Mono (data/code/captions):** `IBM Plex Mono` or `Geist Mono`.
- Tabular figures in all tables and numeric data.

Scale — note the deliberate contrast between display and body (this is what reads as "designed"):
- Display  `48px` / `52px` / `600` / letter-spacing `-0.02em`
- H1       `32px` / `40px` / `600` / `-0.01em`
- H2       `24px` / `32px` / `600`
- H3       `18px` / `26px` / `600`
- Body-lg  `17px` / `28px` / `400`  — lead paragraphs
- Body     `15px` / `24px` / `400`
- Small    `13px` / `20px` / `400`
- Caption  `12px` / `16px` / `500`  — eyebrows/labels, tracking `+0.04em`

Rules: these steps only. Weights allowed: `400, 500, 600, 700`. Body line length ~66–72 chars.

---

## 4. Spacing & layout

- **Base unit 4px. All spacing is a multiple of 4.** Scale: `4, 8, 12, 16, 24, 32, 48, 64, 96`.
- **Content max-width `1200px`**, centered, `24px` gutters. Text-heavy columns cap at `680px`.
- **Section rhythm:** `96px` between major sections on desktop, `64px` mobile.
- **Card padding:** `24px`.
- **12-column grid**, `24px` gutter. Use it; don't stack everything full-width.

Breakpoints: mobile `<640px`, tablet `640–1024px`, desktop `>1024px`.

**Layout guidance (anti-template):**
- The hero states a thesis — the single most characteristic thing about the site. Not a big number + gradient.
- Favor left-aligned structure and intentional asymmetry over centered stacks.
- One signature moment per page; the rest is disciplined and quiet.

---

## 5. Shape, border, elevation

- **Radius:** `8px` default (buttons, inputs, cards), `12px` large containers/modals, `9999px` pills/avatars only. **Never mix rounded and sharp corners in one view. No radius above 12px on structural elements.**
- **Border:** `1px solid --border`. Hairlines carry separation.
- **Elevation:** borders first. Shadow only on overlays: `0 8px 24px rgba(20,22,27,0.10)`. **No shadows on buttons or cards. No glassmorphism.**

---

## 6. Iconography & imagery

- **Icons:** one line-icon set (Lucide). `1.5px` stroke, `20px` default. No filled/outline mixing. **No emoji.**
- **Imagery:** consistent treatment — same corner radius as cards, no drop shadows, no borders. Real content over stock abstraction.
- **Illustration:** flat, palette colors only.

---

## 7. Components

Define every interactive state. "Not specified" = do not render it.

### Button — primary
bg `--accent`, text `#FFFFFF`, radius `8px`, height `40px`, padding `0 16px`, `15px`/`600`
- hover `--accent-hover` · focus `2px` outline `--accent`, `2px` offset · disabled bg `--surface-alt`, text `--text-faint`
- **no shadow, no gradient**

### Button — secondary
transparent bg, text `--text`, border `1px --border`, same sizing · hover bg `--surface-alt`

### Input / textarea
bg `--bg`, border `1px --border`, radius `8px`, height `40px`, padding `0 12px`, placeholder `--text-faint`
- focus: border `--accent` + `3px` ring `--accent-weak` · error: border `--danger`, helper `--danger`

### Card
bg `--surface`, border `1px --border`, radius `12px`, padding `24px`, **no shadow**

### Badge / tag
pill, `--accent-weak` bg, `--accent` text, `12px`/`500`

### Table
header `--text-muted` `12px`/`600` · row-bottom `1px --border` · row hover `--surface-alt` · tabular figures

---

## 8. Motion

- **Duration:** `150ms` micro, `250ms` transitions. Nothing over `300ms`.
- **Easing:** `cubic-bezier(0.2, 0, 0, 1)`.
- Animate `opacity` / `transform` only. No bounce, no auto-playing motion, no scattered scroll effects. One orchestrated moment beats many.
- Respect `prefers-reduced-motion`.

### Named interactions — reuse these, invent no others

The complete animation vocabulary. Four total, all derived from the tokens above.

**1. `hover-transition`** — buttons, links, interactive cards
- Transitions `background-color`, `border-color`, `color` only. `150ms`, `cubic-bezier(0.2, 0, 0, 1)`.
- A clickable card may add `transform: translateY(-2px)`. No shadow, no scale, no color inversion.

**2. `focus-ring`** — every focusable element
- Appears **instantly (0ms)**. Never animate a focus indicator — delay hurts usability.
- `2px` outline `--accent` at `2px` offset; inputs use the `3px --accent-weak` ring from §7.

**3. `reveal`** — section/block entrance on scroll
- `opacity: 0 → 1` and `transform: translateY(8px) → 0`. `250ms`, `cubic-bezier(0.2, 0, 0, 1)`.
- Fires **once**, when ~15% of the element is in view. Small offset only — `8px`, never a long slide.
- Optional sibling stagger: `60ms` apart, **max 5 elements**, first fold only.
- Reduced-motion: fade only, no translate.

**4. `overlay`** — modal, dropdown, popover
- Backdrop: `opacity: 0 → 1`, `150ms`.
- Panel in: `opacity: 0 → 1` + `transform: translateY(4px) → 0`, `200ms`.
- Panel out: reverse, `120ms`. Exits are always faster than entrances.

Everything else is an instant state change. No page-load animation unless the hero *is* the page's signature element — then a single `reveal`, nothing more.

---

## 9. Accessibility & quality floor (non-negotiable)

- Text contrast ≥ **4.5:1** (normal), ≥ 3:1 (large).
- Visible keyboard focus on every interactive element (`--accent` ring).
- Never encode meaning in color alone.
- Minimum interactive target `40×40px`.
- Responsive down to mobile even though desktop is primary.

---

## 10. Rules — do / don't

**Do**
- Use `--accent` for exactly one emphasis per view.
- Keep all spacing on the 4px grid; use the 12-col grid.
- Prefer borders to shadows.
- Reuse the defined type steps, radii, and durations only.
- Set the display typeface and accent deliberately per brand.

**Don't**
- No pure black `#000000`; no low-contrast text on fills.
- No mixing rounded and sharp corners in one view.
- No shadows on buttons/cards; no glassmorphism.
- No second accent, gradient accent, or extra body font.
- No emoji, no decorative 01/02/03, no icon-in-circle feature grids.
- No values outside this file.
