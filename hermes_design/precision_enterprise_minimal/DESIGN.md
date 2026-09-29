---
name: Precision Enterprise Minimal
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#5b403f'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#8f6f6e'
  outline-variant: '#e3bebc'
  surface-tint: '#ba172e'
  primary: '#8c001c'
  on-primary: '#ffffff'
  primary-container: '#b5122b'
  on-primary-container: '#ffc5c3'
  inverse-primary: '#ffb3b1'
  secondary: '#565e74'
  on-secondary: '#ffffff'
  secondary-container: '#dae2fd'
  on-secondary-container: '#5c647a'
  tertiary: '#004a5d'
  on-tertiary: '#ffffff'
  tertiary-container: '#00637c'
  on-tertiary-container: '#95ddfa'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdad8'
  primary-fixed-dim: '#ffb3b1'
  on-primary-fixed: '#410007'
  on-primary-fixed-variant: '#92001d'
  secondary-fixed: '#dae2fd'
  secondary-fixed-dim: '#bec6e0'
  on-secondary-fixed: '#131b2e'
  on-secondary-fixed-variant: '#3f465c'
  tertiary-fixed: '#b9eaff'
  tertiary-fixed-dim: '#89d0ed'
  on-tertiary-fixed: '#001f29'
  on-tertiary-fixed-variant: '#004d62'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: '600'
    lineHeight: 44px
    letterSpacing: -0.03em
  display-lg-mobile:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '600'
    lineHeight: 36px
    letterSpacing: -0.025em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  label-uppercase:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.06em
  label-numeric:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2.5rem
  margin-mobile: 1.25rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

The design system embodies surgical precision, rigorous executive utility, and quiet authority. Designed for mission-critical enterprise decision-making, the interface prioritizes clarity over visual noise, replacing decorative elements with deliberate spatial distribution and structural purity.

### Aesthetic Foundation
- **Philosophical Synthesis**: Combines the mechanical density of developer platforms, the typographical authority of premium fintech infrastructure, and the quiet tactile physical precision of modern industrial tooling.
- **Architectural Rigor**: Relies on a strict structural grid, hairline borders, and pure white planes suspended over an engineered background canvas.
- **Absolute Restraint**: Gradients, atmospheric neon blurs, colored card backgrounds, and decorative illustrations are strictly prohibited. Visual power derives entirely from information density, precise alignment, and deliberate negative space.
- **Cognitive Rule**: Every viewport adheres strictly to the law of singleness: one primary outcome, one dominant data visualization, and one designated primary action.

## Colors

The palette operates under a high-discipline monochromatic governance model punctuated by a single high-precision chromatic focal point.

### Palette Roles
- **Primary Accent (`#B5122B`)**: Precision Crimson. Reserved strictly for primary state commitments: active top-level navigation anchors, primary action buttons, selected radio/toggle nodes, key metric deltas, and critical gap callouts. It must never be applied to broad card backgrounds, decorative iconography, or low-priority utility states.
- **Canvas Base (`#F8F9FA` to `#F4F5F7`)**: The global architectural backdrop. A calibrated, neutral tone that exposes pure white interactive layers without causing eye fatigue.
- **Surface Elevation (`#FFFFFF`)**: Pure White. Dedicated exclusively to distinct interactive cards, elevated panels, modals, and input states.
- **Hairline Border (`#E5E7EB`)**: A uniform 1px structural boundary that defines all modules, data tables, and input perimeters.
- **Text & Hierarchy**:
  - **Ink Primary (`#0F172A`)**: Near-black slate for top-tier headings, numerical KPIs, and dominant data points.
  - **Ink Secondary (`#475569`)**: Mid-tone slate for supporting section headers and secondary actions.
  - **Ink Tertiary (`#64748B`)**: Muted slate for metadata, uppercase table headers, and structural hints.
  - **Border Focus (`#0F172A` / `#B5122B`)**: Crisp single-pixel selection states.

## Typography

The typography uses Inter across all levels, relying on strict size and tracking shifts rather than multiple families to establish rank. The system treats text as functional architecture: long-form prose is minimized in favor of tabular data, atomic key-value pairs, and unambiguous titles.

### Typographical Principles
- **Title Tracking**: Display headlines use heavy negative tracking (`-0.03em`) combined with a semi-bold weight (`600`) to anchor the view with solid visual mass.
- **Label Governance**: Metadata and section tags must be rendered in `label-uppercase` with explicit character tracking (`0.06em`) and uppercase transformation.
- **Tabular Figures**: All numerical metrics, status counts, and tabular coordinates utilize `font-feature-settings: "tnum" 1` to guarantee vertical column alignment across rapidly updating data points.

## Layout & Spacing

Layouts follow an absolute 8pt architectural rhythm, with a supplementary 4pt sub-grid for internal component alignment.

### Grid & Composition
- **Canvas Shell**: A 12-column responsive fluid grid with fixed outer bounds capped at 1440px for ultra-dense management dashboards, expanding cleanly across fluid widths with fixed 40px (`2.5rem`) side margins.
- **Breathing Discipline**: High information density is balanced by wide external margins around visual clusters. Rather than packing elements tightly, individual cards maintain precise internal paddings (`space-md` to `space-lg`) paired with structural gaps (`space-lg` to `space-xl`) between distinct analytical domains.
- **Reflow Architecture**:
  - **Desktop (1024px+)**: Multi-column analytic arrangements (e.g., 8-column dominant chart paired with a 4-column contextual inspection ledger).
  - **Tablet (768px - 1023px)**: Symmetrical 2-column or stacked single-panel modules; side rails collapse to utility bars.
  - **Mobile (<768px)**: Strict single-column stack, preserving full screen margins (`margin-mobile: 1.25rem`) with scrollable horizontal inspection tables.

## Elevation & Depth

Visual hierarchy uses physical precision instead of dramatic drop shadows. Surfaces employ a balanced combination of hairline boundaries and faint, directional micro-shadows that suggest clean mechanical planes rather than soft layers.

### Layering Rules
- **Flat Background**: The canvas base (`#F8F9FA`) remains completely unshadowed.
- **Resting Layer (Surface 1)**: Pure white (`#FFFFFF`) containers, cards, and input fields sit directly on the canvas, bounded by a 1px solid hairline border (`#E5E7EB`). Depth is introduced via a dual micro-offset:
  - Top edge highlight: `0px 1px 0px 0px rgba(255, 255, 255, 0.9) inset`
  - Bottom edge definition: `0px 1px 2px 0px rgba(15, 23, 42, 0.04), 0px 0px 1px 0px rgba(15, 23, 42, 0.03)`
- **Interactive Hover Layer**: Hovering over interactive rows or cards adds an extremely subtle base lift:
  - `0px 3px 6px -1px rgba(15, 23, 42, 0.05), 0px 1px 2px 0px rgba(15, 23, 42, 0.03)`
  - The perimeter border sharpens to `#D1D5DB`.
- **Floating Overlays (Modals, Dropdowns)**: Reserved for menus and dialog overlays. Suspended cleanly with structured edges and controlled ambient diffusion:
  - `0px 10px 24px -4px rgba(15, 23, 42, 0.08), 0px 2px 6px -1px rgba(15, 23, 42, 0.04)`
  - Fully opaque pure white surface (`#FFFFFF`) with a 1px solid border (`#E5E7EB`). Never use blur filters or translucent backgrounds.

## Shapes

The design system maintains a geometric, compact profile. Sharp, intentional transitions reinforce the system's focus on engineering precision over casual software styling.

### Corner Radii
- **Standard UI Elements (`0.25rem` / `4px`)**: Applied consistently to primary buttons, input fields, checkboxes, data tags, and table row selection envelopes.
- **Card Containers & Panels (`0.5rem` / `8px`)**: Reserved for structural data cards, modal containers, and dashboard analytical modules (`rounded-lg`).
- **Pill Exceptions**: Strictly forbidden for buttons and standard inputs. The pill shape (`9999px`) is applied exclusively to miniature numeric notification counters and system-critical health status chips.

## Components

Components are stripped of decorative ornamentation. Visual hierarchy is established through precise typography, hairline borders, and targeted applications of the Precision Crimson accent.

### Buttons
- **Primary**: Solid background in Precision Crimson (`#B5122B`), pure white text (`#FFFFFF`), font weight `500`, subtle inset top edge highlight (`rgba(255,255,255,0.15)`), radius `4px`. Hover transitions to `#9B0F24`. Active click triggers a direct `scale(0.99)` transform.
- **Secondary**: Pure white background (`#FFFFFF`), hairline border (`#E5E7EB`), text color `#0F172A`. Hover shifts background to `#F8F9FA` and border to `#D1D5DB`.
- **Ghost / Utility**: Transparent background, text color `#475569`, radius `4px`. Hover reveals `#F1F5F9`.

### Input Fields & Controls
- **Text Inputs**: Flat `#FFFFFF` fill, 1px solid `#E5E7EB` border, internal padding `8px 12px`, text size `13px`. Placeholder text uses `#94A3B8`. Active focus shifts the border to `#0F172A` with a crisp `0 0 0 1px #0F172A` box-shadow. Precision Crimson focus is reserved strictly for invalid/error validation states.
- **Checkboxes & Radios**: 16px square/circle with a 1px border (`#D1D5DB`). When checked, fills with Precision Crimson (`#B5122B`) displaying a pure white 1.5px geometric check icon.

### Cards & Analytical Modules
- **Container**: White (`#FFFFFF`) canvas, hairline border (`#E5E7EB`), radius `8px`, micro-elevation dual shadow.
- **Header**: Standardized height with an uppercase, wide-tracked category tag (`11px`, `#64748B`), an adjacent medium value or context label, and an optional right-aligned utility control. 
- **Internal Separators**: Dividers must be 1px hairline rules (`#F1F5F9`), maintaining alignment with outer edge padding.

### Chips & Status Indicators
- **Metric Chips**: Background `#F8F9FA`, hairline border (`#E5E7EB`), text `#475569`, uppercase `11px`, weight `600`.
- **Alert / Gap Tag**: Reserved exclusively for performance bottlenecks or critical gaps. Fill `#FFF1F2`, border `#FECDD3`, text `#B5122B`, dot indicator `6px` solid `#B5122B`.

### Iconography
- Rendered strictly at `1.5px` uniform line stroke.
- Sized cleanly on a `16x16` or `20x20` bounding box.
- Color inherits directly from parent text ink (`currentColor`); icons never carry independent decorative colors.