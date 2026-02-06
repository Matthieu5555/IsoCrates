# Frontend Style Guide

This guide defines the spacing, typography, and design patterns used throughout the IsoCrates frontend application.

## Design System Files

- `lib/styles/spacing.ts` - Centralized spacing scale and semantic spacing patterns
- `lib/styles/typography.ts` - Typography scale for headings, body text, and labels
- `lib/styles/button-variants.ts` - Comprehensive component variants and style patterns

## Spacing System

### Component Padding

**Inputs:**
- Default inputs: `px-4 py-2.5`
- Textareas: `px-4 py-3`
- Search inputs: `px-4 py-2`

**Buttons:**
- Standard buttons: `px-4 py-2` (minimum for proper touch targets)
- Icon buttons: `p-2`
- Small icon buttons: `px-2 py-1`

**Cards & Containers:**
- Large cards: `p-6`
- Compact cards: `p-4`
- Page containers: `p-4 md:p-8` (responsive)

**Dialogs:**
- Header: `px-6 py-5`
- Body: `px-6 py-6`
- Footer: `px-6 py-5`
- Container: `px-4` (mobile safety margin)

### Gaps Between Elements

Use these gap values for flexbox and grid layouts:

- **Tight (related items):** `gap-2` (8px) - For closely related controls
- **Default:** `gap-3` (12px) - Standard spacing between elements
- **Sections:** `gap-4` (16px) - Between logical sections
- **Major sections:** `gap-6` (24px) - Between major page sections

### Vertical Spacing (Stack Layouts)

Use `space-y-*` classes for vertical stacking:

- **Form fields:** `space-y-6` (24px) - Between form fields
- **Card content:** `space-y-4` (16px) - Within cards
- **List items:** `space-y-3` (12px) - Between list items
- **Page sections:** `space-y-8` (32px) - Major page sections

### Labels and Helper Text

- **Label margin:** `mb-3` (12px minimum, never less than `mb-2`)
- **Helper text margin:** `mt-2.5` (10px)
- **Error text margin:** `mt-2` (8px)

### Responsive Design

Always consider mobile viewports when adding spacing:

- **Page padding:** `p-4 md:p-8`
- **Dialog containers:** `px-4` for mobile safety
- **Top bar:** `px-4 md:px-6`
- **Sections:** Use responsive utilities when needed

## Interactive Elements

### Minimum Touch Targets

All clickable elements must meet the **40x40px minimum touch target** for accessibility and mobile usability:

- **Buttons:** `px-4 py-2` minimum
- **List items:** `py-2.5` minimum (combined with padding for full height)
- **Tree nodes:** `py-2` minimum
- **Menu items:** `py-2.5` for comfortable clicking

### Transitions

Add smooth state transitions to all interactive elements:

```tsx
className="... hover:bg-accent transition-colors"
```

Standard transitions:
- `transition-colors` - For background and text color changes
- `transition-all` - For multiple properties (use sparingly for performance)

## Typography

### Headings

Use the semantic heading classes from `typography.ts`:

```tsx
import { typography } from '@/lib/styles/typography';

<h1 className={typography.heading.h1}>Main Title</h1>
<h2 className={typography.heading.h2}>Section Title</h2>
<h3 className={typography.heading.h3}>Subsection Title</h3>
```

All headings include consistent margin-bottom for proper visual hierarchy.

### Body Text

```tsx
import { typography } from '@/lib/styles/typography';

<p className={typography.body.default}>Standard text</p>
<p className={typography.body.large}>Larger text</p>
<p className={typography.body.small}>Small text</p>
```

### Labels

Always use consistent label styling:

```tsx
import { typography } from '@/lib/styles/typography';

<label className={typography.label.default}>Field Label</label>
<label className={typography.label.small}>Small Label</label>
```

Or use the variant directly:
```tsx
<label className="block text-sm font-medium mb-3">Field Label</label>
```

**Never use less than `mb-2` for labels!**

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

All dialogs and context menus **must** use `createPortal` from `react-dom` to render at `document.body`. This prevents overflow clipping when the component is mounted inside a scrollable container (e.g., the sidebar).

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

❌ **Don't do this:**
```tsx
<div className="px-2 py-1 space-y-2">
```

✅ **Do this:**
```tsx
<div className={formFieldVariants.container}>
```

### 2. Maintain Visual Hierarchy

Ensure adequate spacing to distinguish sections:
- Use larger gaps between unrelated sections
- Use smaller gaps for related items
- Consistent spacing creates predictable layouts

### 3. Mobile First

Always consider mobile viewports:
- Test on small screens
- Use responsive utilities
- Ensure touch targets are adequate

### 4. Accessibility

- Minimum 40x40px touch targets
- Clear focus states (handled by variants)
- Adequate spacing for readability
- Proper semantic HTML

### 5. Performance

- Prefer `transition-colors` over `transition-all`
- Avoid excessive animations
- Use CSS transforms for layout shifts

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

Custom scrollbars in `app/globals.css`:
- Thin scrollbars (8px width/height)
- Theme-aware colors using CSS variables
- Rounded corners, hover effects
- Cross-browser support (Firefox and Chromium)
- Global `scroll-behavior: smooth` on `<html>`

### When to Use Each Variant

| Variant | Use For |
|---------|---------|
| `vertical` | Long lists, article content, sidebar navigation |
| `horizontal` | Wide tables, code blocks |
| `maxHeight50/75` | Component sections that shouldn't dominate the page (version history, comments) |
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

- **AppShell** -- Main content `overflow-y-auto`, sidebar independent scroll
- **DocumentView** -- Editor textarea scrolls, preview uses page scroll
- **MetadataDetails** -- Table wrapper horizontal scroll on mobile
- **VersionHistory** -- `maxHeight50` (scrolls if > 50vh)
- **SearchCommand** -- `contentArea` with smooth scroll
- **Dialog Components** -- Body `max-h-[60vh]` with vertical scroll
- **DocumentTree** -- `overflow-y-auto` for long lists
- **Markdown Content** -- Code blocks horizontal scroll, tables horizontal scroll on mobile

### Scrolling Best Practices

- Avoid nested `overflow: auto` containers unnecessarily
- For very long lists (1000+ items), consider virtualization (`react-virtual`, `react-window`)
- Ensure parent has defined height (`h-screen`, `max-h-[50vh]`) for scroll to work
- Use `overscroll-contain` on mobile to prevent bounce effects
- `scroll-smooth` uses GPU acceleration

### Scrolling Troubleshooting

- **Container doesn't scroll**: Ensure parent has defined height and no `overflow: hidden`
- **Scrollbar not visible**: Some browsers hide by default; scrollbars appear on hover
- **Entire page scrolls horizontally**: Check for elements > 100vw; use scroll containers for tables/code
- **iOS bounce**: Use `scrollContainerVariants.mobileScroll` or `overscroll-contain`

---

## Maintenance

When adding new components:

1. **Check existing variants first** - Reuse before creating new
2. **Add to button-variants.ts** - If it's a reusable pattern
3. **Document here** - Update this guide with new patterns
4. **Test responsive** - Verify on mobile and desktop
5. **Verify accessibility** - Check touch targets and focus states

## Success Criteria

A well-designed component should:

✅ Use design tokens from the style system
✅ Have adequate spacing (not cramped)
✅ Meet 40x40px minimum touch targets
✅ Include smooth transitions
✅ Work well on mobile
✅ Follow consistent patterns
✅ Be maintainable and clear
