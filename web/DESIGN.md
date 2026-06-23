# DESIGN.md — Cal.com design language

> Generated to mirror `npx getdesign@latest add cal`. These are the UI
> conventions the app follows. (Re-run the command to refresh from source.)

## Principles
- **Calm and neutral.** A near-monochrome palette; color is reserved for intent
  (destructive red, the occasional accent). Let content and whitespace carry the
  design.
- **Quiet surfaces, crisp borders.** 1px hairline borders (`--border`) separate
  regions instead of heavy shadows. Cards sit just off the background.
- **Compact, legible typography.** Inter, 13–14px body, medium weight for labels,
  generous line-height. Uppercase micro-labels for metadata.
- **Soft geometry.** `--radius: 0.5rem`; `rounded-md` everywhere, pills for tags.
- **Restrained motion.** Subtle hover state changes; a single blinking caret for
  streaming. No bouncy animation.

## Tokens
Defined as HSL CSS variables in `src/index.css` (`:root` + `.dark`) and wired to
Tailwind in `tailwind.config.js`: `background, foreground, card, primary,
secondary, muted, accent, destructive, border, input, ring`.

## Components
shadcn/ui primitives (`src/components/ui/*`) themed with the tokens above:
`button` (default/secondary/ghost/outline/destructive), `textarea`, `badge`,
`dropdown-menu`. Layout favors a fixed left rail + a single focused content
column (max-w-3xl) for the conversation.
