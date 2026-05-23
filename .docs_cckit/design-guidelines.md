# Design Guidelines & UI/UX Standards

**Version:** 2.17.0  
**Last Updated:** 2026-05-14  
**Scope:** Boilerplate template (customize for your project)

## Overview

This document provides design and UX guidelines for projects built with claudekit-engineer. Since this is a **template boilerplate**, specific design decisions depend on your project's domain (web app, API, CLI tool, etc.). Use these guidelines as a foundation; customize per your product requirements.

## Design Philosophy

### Core Principles

**1. User-Centric Design**
- Design for the end user first; internal tooling second
- Validate designs with real users before implementation
- Iterate based on feedback; avoid "design by committee"

**2. Clarity Over Cleverness**
- Prioritize clear communication over visual innovation
- Use established patterns and conventions
- Help users understand the system without documentation

**3. Consistency**
- Maintain visual and interaction consistency across the product
- Use a documented design system (colors, typography, spacing)
- Apply the same patterns to similar problems

**4. Accessibility**
- WCAG 2.1 AA compliance minimum
- Support keyboard navigation and screen readers
- Provide text alternatives for images and icons
- Test with real accessibility tools and users

## Design System Components

### Color Palette

Define a base color palette for your project:

| Purpose | Color | Usage |
|---------|-------|-------|
| Primary | `#0066CC` (blue) | Calls-to-action, primary UI |
| Secondary | `#6C757D` (gray) | Secondary actions, disabled states |
| Success | `#28A745` (green) | Confirmation, success messages |
| Warning | `#FFC107` (yellow) | Caution, non-critical warnings |
| Error | `#DC3545` (red) | Errors, destructive actions |
| Neutral | `#F8F9FA` (light gray) | Backgrounds, dividers |

**Recommendation**: Use a tool like [Coolors](https://coolors.co) or your design tool to generate accessible color combinations.

### Typography

| Element | Font | Size | Weight | Line Height |
|---------|------|------|--------|-------------|
| H1 (Title) | System sans-serif | 28-32px | 600 | 1.2 |
| H2 (Heading) | System sans-serif | 20-24px | 600 | 1.3 |
| H3 (Subheading) | System sans-serif | 16-18px | 600 | 1.4 |
| Body | System sans-serif | 14-16px | 400 | 1.5 |
| Small | System sans-serif | 12-14px | 400 | 1.4 |
| Code | Monospace | 12-14px | 400 | 1.5 |

**Recommendation**: Use system fonts (sans-serif) for performance and consistency.

### Spacing & Layout

Use a consistent spacing scale (4px, 8px, 12px, 16px, 24px, 32px, 48px):

| Element | Spacing |
|---------|---------|
| Component padding | 12-16px |
| Margin between sections | 24-32px |
| Margin between cards | 16-24px |
| Grid gap | 16-24px |

**Recommendation**: Use CSS variables for easy global adjustments.

## User Interface Patterns

### Navigation
- **Top navigation**: Global navigation for web apps
- **Sidebar**: Context-specific navigation for dashboards
- **Tabs**: Switch between related content
- **Breadcrumbs**: Show current location in hierarchy

**Best Practices**:
- Show current page/section clearly
- Limit top-level navigation to 5-7 items
- Group related items together
- Provide search for large navigation structures

### Forms
- **Label placement**: Above input fields (top-aligned)
- **Input height**: 32-40px minimum for touch targets
- **Validation**: Real-time feedback with clear error messages
- **Submit buttons**: Disabled until form is valid (for destructive actions)

**Pattern**:
```
Label (optional - required indicator)
  [Input field with placeholder text]
Error message (if applicable)
```

### Modals & Dialogs
- **Use when**: Demand immediate attention or require focused input
- **Avoid**: For navigation or low-priority tasks
- **Backdrop**: Dim background to focus attention
- **Keyboard support**: Escape to close (with confirmation if data loss)

### Loading States
- **Spinner**: Indeterminate loading
- **Progress bar**: For long operations (>2 seconds)
- **Skeleton screens**: Placeholder for content being loaded
- **Message**: "Loading..." or "Please wait..."

### Empty States
- **Icon**: Visual representation of emptiness
- **Headline**: "No {items} yet"
- **Description**: Brief explanation or helpful suggestion
- **CTA**: Action to create first item (if applicable)

## Accessibility Standards

### Visual Accessibility

| Standard | Requirement | Example |
|----------|------------|---------|
| Color contrast | 4.5:1 for text; 3:1 for UI | Use contrast checker tools |
| Focus indicators | Visible keyboard focus | Blue outline on interactive elements |
| Font size | Min 12px for body text | Increase for older audiences |
| Line length | 45-75 characters per line | Use max-width on text blocks |

### Interaction Accessibility

- **Keyboard navigation**: Tab through all interactive elements in logical order
- **Screen readers**: Proper semantic HTML; aria-labels for icons
- **Skip links**: Jump to main content (for web)
- **Alternative text**: Meaningful alt text for images
- **Captions**: Provide captions for videos

### Motion & Animation

- **Avoid**: Flashing content (>3 times/second) — risk of seizures
- **Respect**: `prefers-reduced-motion` CSS media query
- **Keep**: Animations under 300ms for snappy feedback
- **Purpose**: Use motion to guide attention, not distract

## Responsive Design

### Breakpoints

| Device | Width | Layout |
|--------|-------|--------|
| Mobile | < 640px | Single column, large touch targets |
| Tablet | 640px - 1024px | Two-column, flexible layout |
| Desktop | > 1024px | Multi-column, optimized for mouse |

**Approach**: Mobile-first; enhance for larger screens.

### Touch Targets
- **Minimum**: 44x44px (Apple recommendation)
- **Spacing**: 8px minimum between targets
- **Buttons**: Easily tappable; avoid tiny buttons

### Viewport Configuration
```html
<meta name="viewport" content="width=device-width, initial-scale=1">
```

## Interaction Patterns

### Feedback & Validation

**Inline validation** (as user types):
- Show error immediately when criteria not met
- Provide helpful suggestions
- Avoid red/green color alone (accessibility)

**Toast notifications** (temporary alerts):
- Position: Bottom-right (out of main content)
- Duration: 3-5 seconds (auto-dismiss)
- Types: Success (green), Error (red), Info (blue), Warning (yellow)

**Confirmation dialogs** (destructive actions):
- Require explicit confirmation for delete/irreversible actions
- Disable undo after confirmation
- Example: "Are you sure you want to delete [item]? This cannot be undone."

### Microcopy

Write clear, concise UI copy:

| Context | Good | Bad |
|---------|------|-----|
| Button | "Save changes" | "OK" |
| Error | "Email must be valid (e.g., user@example.com)" | "Invalid input" |
| Placeholder | "you@example.com" | "Email" |
| Empty state | "No tasks yet. Create one to get started." | "No data" |

## Dark Mode Support

If supporting dark mode:
- Maintain sufficient contrast in both modes
- Use CSS variables for theme-aware colors
- Test both modes with real users
- Provide system preference detection

Example:
```css
:root {
  --bg-primary: #ffffff;
  --text-primary: #000000;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg-primary: #1a1a1a;
    --text-primary: #ffffff;
  }
}
```

## Design Handoff to Development

### Documentation
- Include design rationale (why this design?)
- Define component variants (default, hover, disabled, loading)
- Specify animation timings and easing
- Provide accessibility requirements

### Tools & Specifications
- Use tools: Figma, Adobe XD, or Sketch
- Export components as detailed specs
- Provide assets in multiple formats (SVG, PNG 2x, 3x)
- Maintain a living component library

### Quality Assurance
- **Designer reviews**: Before moving to development
- **Developer implements**: Per spec, can propose improvements
- **QA validates**: Matches design in all states
- **Accessibility audit**: Before release

## Testing & Validation

### User Testing
- **Goals**: Validate assumptions, identify pain points
- **Frequency**: Every major feature or redesign
- **Sample size**: 5-8 users per test (diminishing returns)
- **Methods**: Usability testing, surveys, analytics

### Usability Heuristics (Nielsen Norman)
1. System visibility (keep users informed)
2. System-to-user match (use user's language)
3. User control and freedom (undo/redo)
4. Consistency and standards (familiar patterns)
5. Error prevention and recovery (clear errors)
6. Recognition vs. recall (minimize memory)
7. Flexibility and efficiency (shortcuts for power users)
8. Aesthetic and minimalist design (remove clutter)
9. Error messages (plain language, solutions)
10. Help and documentation (task-focused help)

## Design Debt & Maintenance

### Refactoring Triggers
- Inconsistent component usage (>2 variants doing same thing)
- Design system lag (>3 UI updates not documented)
- Accessibility issues discovered during audit
- Performance problems from over-engineered animations

### Review Process
- **Design review**: Monthly (or per release)
- **Accessibility audit**: Quarterly
- **User testing**: After major features
- **Component audit**: Annually

## Related Guidelines

- **[Code Standards](./code-standards.md)** — Frontend implementation patterns
- **[System Architecture](./system-architecture.md)** — Data flow context
- **[Deployment Guide](./deployment-guide.md)** — Design system asset deployment

## Tools & Resources

### Design Tools
- **Figma** — Collaborative design (recommended for teams)
- **Adobe XD** — Professional UI/UX design
- **Sketch** — macOS-focused design tool

### Accessibility
- **WAVE** — Web accessibility evaluation tool
- **Axe DevTools** — Browser accessibility checker
- **NVDA** — Free screen reader (Windows)
- **WCAG Guidelines** — Web Content Accessibility Guidelines 2.1

### Color & Contrast
- **Coolors** — Palette generator
- **WebAIM Contrast Checker** — Verify contrast ratios
- **Color Blindness Simulator** — Test for colorblind accessibility

### Feedback
- **Maze** — User testing platform
- **UserTesting** — Remote usability testing
- **Hotjar** — Heatmaps and session recordings
