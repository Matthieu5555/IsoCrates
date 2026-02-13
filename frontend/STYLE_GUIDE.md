# Frontend Style Guide

This guide defines the spacing, typography, and design patterns used throughout the IsoCrates frontend application. Think of it as a single source of truth for how components should look and feel, so every part of the UI stays visually consistent.

## Design System Files

The style system lives in three files. `lib/styles/spacing.ts` holds the centralized spacing scale and semantic spacing patterns. `lib/styles/typography.ts` defines the typography scale for headings, body text, and labels. `lib/styles/button-variants.ts` contains comprehensive component variants and style patterns.

## Spacing System

### Component Padding

| Element | Classes |
|---------|---------|
| Default inputs | `px-4 py-2.5` |
| Textareas | `px-4 py-3` |
| Search inputs | `px-4 py-2` |
| Standard buttons | `px-4 py-2` (minimum for proper touch targets) |
| Icon buttons | `p-2` |
| Small icon buttons | `px-2 py-1` |
| Large cards | `p-6` |
| Compact cards | `p-4` |
| Page containers | `p-4 md:p-8` (responsive) |
| Dialog header | `px-6 py-5` |
| Dialog body | `px-6 py-6` |
| Dialog footer | `px-6 py-5` |
| Dialog container | `px-4` (mobile safety margin) |

### Gaps Between Elements

Use these gap values for flexbox and grid layouts.

| Purpose | Class | Size |
|---------|-------|------|
| Tight (related items) | `gap-2` | 8px |
| Default | `gap-3` | 12px |
| Sections | `gap-4` | 16px |
| Major sections | `gap-6` | 24px |

### Vertical Spacing (Stack Layouts)

Use `space-y-*` classes for vertical stacking.

| Purpose | Class | Size |
|---------|-------|------|
| Form fields | `space-y-6` | 24px |
| Card content | `space-y-4` | 16px |
| List items | `space-y-3` | 12px |
| Page sections | `space-y-8` | 32px |

### Labels and Helper Text

Labels get `mb-3` (12px minimum, never less than `mb-2`). Helper text uses `mt-2.5` (10px). Error text uses `mt-2` (8px).

### Responsive Design

Always consider mobile viewports when adding spacing. Pages use `p-4 md:p-8`. Dialog containers use `px-4` for mobile safety. The top bar uses `px-4 md:px-6`. Apply responsive utilities to sections when needed.

## Interactive Elements

### Minimum Touch Targets

All clickable elements must meet the 40x40px minimum touch target for accessibility and mobile usability. Buttons need `px-4 py-2` at minimum. List items need `py-2.5` minimum (combined with padding for full height). Tree nodes need `py-2` minimum. Menu items use `py-2.5` for comfortable clicking.

### Transitions

Add smooth state transitions to all interactive elements:

```tsx
className="... hover:bg-accent transition-colors"
```

Prefer `transition-colors` for background and text color changes. Reserve `transition-all` for cases involving multiple properties, and use it sparingly for performance reasons.

## Typography

### Headings

Use the semantic heading classes from `typography.ts`. All headings include consistent margin-bottom for proper visual hierarchy.

```tsx
import { typography } from '@/lib/styles/typography';

<h1 className={typography.heading.h1}>Main Title</h1>
<h2 className={typography.heading.h2}>Section Title</h2>
<h3 className={typography.heading.h3}>Subsection Title</h3>
```

### Body Text

```tsx
import { typography } from '@/lib/styles/typography';

<p className={typography.body.default}>Standard text</p>
<p className={typography.body.large}>Larger text</p>
<p className={typography.body.small}>Small text</p>
```

### Labels

Always use consistent label styling. Never use less than `mb-2` for labels.

```tsx
import { typography } from '@/lib/styles/typography';

<label className={typography.label.default}>Field Label</label>
<label className={typography.label.small}>Small Label</label>
```

Or use the variant directly:
```tsx
<label className="block text-sm font-medium mb-3">Field Label</label>
```

## Component Variants

### Import Pattern

```tsx
import {
  // Layout & containers
  containerVariants,
  dialogVariants,
  listVariants,
  tableVariants,

  // Form elements
  formFieldVariants,
  inputVariants,
  buttonVariants,

  // Text & badges
  textVariants,
  badgeVariants,
  statusBadgeVariants,

  // Interactive elements
  menuItemVariants,
  contextMenuVariants,
  kbdVariants,

  // Visual
  iconVariants,
  linkVariants,
  overlayVariants,

  // Scrolling
  scrollContainerVariants,
} from '@/lib/styles/button-variants';
```

### Context Menus

Context menus use `createPortal` and dedicated variants:

```tsx
import { contextMenuVariants, menuItemVariants } from '@/lib/styles/button-variants';

<div className={contextMenuVariants.container} style={{ left: x, top: y }}>
  <button className={menuItemVariants.default}>
    <FileText className="h-4 w-4" />
    New Document
  </button>
  <div className={contextMenuVariants.divider} />
  <button className={menuItemVariants.danger}>
    <Trash2 className="h-4 w-4" />
    Delete
  </button>
</div>
```

### Keyboard Shortcuts

```tsx
import { kbdVariants } from '@/lib/styles/button-variants';

// Small kbd (used in footers, inline hints)
<kbd className={kbdVariants.default}>ESC</kbd>

// Larger kbd (used in command trigger buttons)
<kbd className={kbdVariants.trigger}>⌘K</kbd>
```

### Text Utilities

```tsx
import { textVariants } from '@/lib/styles/button-variants';

<span className={textVariants.mutedSm}>Secondary text</span>
<span className={textVariants.mutedXs}>Fine print</span>
```

### Badges

```tsx
import { badgeVariants, statusBadgeVariants } from '@/lib/styles/button-variants';

// Document type badges
<span className={badgeVariants.docTypeClient}>client</span>
<span className={badgeVariants.docTypeServer}>server</span>

// Author badges
<span className={badgeVariants.authorAi}>AI</span>
<span className={badgeVariants.authorHuman}>HUMAN</span>

// Generic badge
<span className={badgeVariants.default}>label</span>

// Status badges
<span className={statusBadgeVariants.current}>Current</span>
```

### Form Fields

```tsx
<div className={formFieldVariants.container}>
  <div className={formFieldVariants.field}>
    <label className={formFieldVariants.label}>Label</label>
    <input className={inputVariants.default} />
    <p className={formFieldVariants.helper}>Helper text</p>
  </div>

  <div className={formFieldVariants.field}>
    <label className={formFieldVariants.label}>Another Field</label>
    <textarea className={inputVariants.textarea} />
  </div>
</div>
```

### Dialogs

All dialogs and context menus must use `createPortal` from `react-dom` to render at `document.body`. This prevents overflow clipping when the component is mounted inside a scrollable container (e.g., the sidebar).

```tsx
import { createPortal } from 'react-dom';

// Always wrap the dialog markup in createPortal:
return createPortal(
  <div className={dialogVariants.overlay}>
    <div className={`${dialogVariants.container} max-w-2xl`}>
      <div className={dialogVariants.content}>
        <div className={dialogVariants.header}>
          <h2 className={dialogVariants.title}>Dialog Title</h2>
        </div>
        <div className={dialogVariants.body}>
          Content goes here
        </div>
        <div className={dialogVariants.footer}>
          <button className={buttonVariants.secondary}>Cancel</button>
          <button className={buttonVariants.primary}>Confirm</button>
        </div>
      </div>
    </div>
  </div>,
  document.body
);
```

### Containers

```tsx
// Page wrapper
<div className={containerVariants.page}>
  <div className={containerVariants.section}>
    <div className={containerVariants.card}>
      Card content
    </div>
  </div>
</div>
```

### Lists

```tsx
<div className={listVariants.container}>
  <div className={listVariants.item}>List item 1</div>
  <div className={listVariants.item}>List item 2</div>
</div>

// Compact variant
<div className={listVariants.container}>
  <div className={listVariants.itemCompact}>Compact item 1</div>
  <div className={listVariants.itemCompact}>Compact item 2</div>
</div>
```

### Tables

```tsx
<table>
  <thead>
    <tr className={tableVariants.row}>
      <th className={tableVariants.header}>Header</th>
    </tr>
  </thead>
  <tbody>
    <tr className={tableVariants.row}>
      <td className={tableVariants.cell}>Cell content</td>
    </tr>
  </tbody>
</table>
```

## Best Practices

### 1. Always Use Design Tokens

Hardcoding Tailwind classes directly means spacing values drift over time, like a recipe where everyone eyeballs the measurements. Use the variant objects instead, so every component draws from the same source.

Bad:
```tsx
<div className="px-2 py-1 space-y-2">
```

Good:
```tsx
<div className={formFieldVariants.container}>
```

### 2. Maintain Visual Hierarchy

Adequate spacing is what tells users which elements belong together and which are separate, the same way paragraph breaks and whitespace work in a book. Use larger gaps between unrelated sections and smaller gaps for related items. Consistent spacing creates predictable layouts.

### 3. Mobile First

Always consider mobile viewports. Test on small screens, use responsive utilities, and ensure touch targets are adequate.

### 4. Accessibility

Maintain 40x40px minimum touch targets. Keep clear focus states (handled by the variants). Use adequate spacing for readability. Use proper semantic HTML.

### 5. Performance

Prefer `transition-colors` over `transition-all`. Avoid excessive animations. Use CSS transforms for layout shifts.

## Common Patterns

### Form with Multiple Fields

```tsx
<form className={formFieldVariants.container}>
  <div className={formFieldVariants.field}>
    <label className={formFieldVariants.label}>Name</label>
    <input className={inputVariants.default} />
    <p className={formFieldVariants.helper}>Enter your full name</p>
  </div>

  <div className={formFieldVariants.field}>
    <label className={formFieldVariants.label}>Description</label>
    <textarea className={inputVariants.textarea} />
  </div>

  <div className="flex gap-3 justify-end">
    <button className={buttonVariants.secondary}>Cancel</button>
    <button className={buttonVariants.primary}>Submit</button>
  </div>
</form>
```

### Card with List

```tsx
<div className={containerVariants.card}>
  <h3 className="text-lg font-semibold mb-4">Items</h3>
  <div className={listVariants.container}>
    {items.map(item => (
      <div key={item.id} className={listVariants.item}>
        {item.name}
      </div>
    ))}
  </div>
</div>
```

### Responsive Page Layout

```tsx
<div className={containerVariants.page}>
  <h1 className={typography.heading.h1}>Page Title</h1>

  <div className={containerVariants.section}>
    <div className={containerVariants.card}>
      <h2 className={typography.heading.h3}>Section Title</h2>
      <div className="space-y-4">
        {/* Content */}
      </div>
    </div>
  </div>
</div>
```

## Scrolling System

### Scroll Container Variants

Located in `lib/styles/button-variants.ts`:

```typescript
scrollContainerVariants = {
  // Basic scroll directions
  vertical: "overflow-y-auto overflow-x-hidden",
  horizontal: "overflow-x-auto overflow-y-hidden",
  both: "overflow-auto",

  // Max height variants
  maxHeightScreen: "max-h-screen overflow-y-auto",
  maxHeight75: "max-h-[75vh] overflow-y-auto",
  maxHeight50: "max-h-[50vh] overflow-y-auto",

  // Component-specific
  dialogBody: "overflow-y-auto max-h-[60vh]",
  sidebarContent: "overflow-y-auto flex-1",
  codeBlock: "overflow-x-auto rounded-md bg-muted p-4",
  tableWrapper: "overflow-x-auto -mx-6 px-6",
  contentArea: "overflow-y-auto scroll-smooth",
  mobileScroll: "overflow-y-auto overscroll-contain",
}
```

### Global Scrollbar Styling

Custom scrollbars are defined in `app/globals.css`. They use thin scrollbars (8px width/height), theme-aware colors via CSS variables, rounded corners with hover effects, and cross-browser support for both Firefox and Chromium. Global `scroll-behavior: smooth` is applied on `<html>`.

### When to Use Each Variant

| Variant | Use For |
|---------|---------|
| `vertical` | Long lists, article content, sidebar navigation |
| `horizontal` | Wide tables, code blocks |
| `maxHeight50/75` | Component sections that should not dominate the page (version history, comments) |
| `dialogBody` | Modal content that might be long |
| `contentArea` | Main content areas, search results (smooth scroll) |
| `mobileScroll` | Mobile-first components where bounce effect is undesirable |

### Usage Examples

```tsx
// Version history (limited height)
<div className={`space-y-3 ${scrollContainerVariants.maxHeight50}`}>
  {versions.map(version => ...)}
</div>

// Metadata table (horizontal scroll on mobile)
<div className={scrollContainerVariants.horizontal}>
  <table className="w-full">...</table>
</div>

// Dialog body (already included in dialogVariants.body)
<div className={dialogVariants.body}>
  {/* includes overflow-y-auto max-h-[60vh] scroll-smooth */}
  {content}
</div>
```

### Components Using Scroll System

The **AppShell** uses `overflow-y-auto` on the main content area, with the sidebar scrolling independently. **DocumentView** scrolls the editor textarea while the preview uses page scroll. **MetadataDetails** wraps its table for horizontal scroll on mobile. **VersionHistory** uses `maxHeight50` so it scrolls when content exceeds 50vh. **SearchCommand** uses `contentArea` with smooth scroll. **Dialog Components** cap the body at `max-h-[60vh]` with vertical scroll. **DocumentTree** applies `overflow-y-auto` for long lists. **Markdown Content** uses horizontal scroll for code blocks and tables on mobile.

### Scrolling Best Practices

Avoid nesting `overflow: auto` containers unnecessarily. For very long lists (1000+ items), consider virtualization with `react-virtual` or `react-window`. Make sure the parent has a defined height (`h-screen`, `max-h-[50vh]`) for scroll to work. Use `overscroll-contain` on mobile to prevent bounce effects. Note that `scroll-smooth` uses GPU acceleration.

### Scrolling Troubleshooting

If a **container does not scroll**, ensure the parent has a defined height and no `overflow: hidden`. If the **scrollbar is not visible**, some browsers hide scrollbars by default and only show them on hover. If the **entire page scrolls horizontally**, check for elements wider than 100vw and wrap tables and code in scroll containers. For **iOS bounce**, use `scrollContainerVariants.mobileScroll` or add `overscroll-contain`.

---

## Maintenance

When adding new components, check existing variants first and reuse before creating new ones. If a pattern is reusable, add it to `button-variants.ts`. Update this guide with any new patterns. Test on both mobile and desktop. Verify accessibility by checking touch targets and focus states.

## Success Criteria

A well-designed component uses design tokens from the style system, has adequate spacing (not cramped), meets the 40x40px minimum touch target, includes smooth transitions, works well on mobile, follows consistent patterns, and is maintainable and clear.
