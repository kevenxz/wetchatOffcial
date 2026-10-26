/**
 * TypeScript mirror of the design tokens that antd's `ThemeConfig` also needs.
 *
 * Why this exists: the token values live in CSS (`tokens.css`) because that is what
 * components consume, but antd needs the same handful of values in JavaScript. Two
 * copies of a palette inevitably drift, so this module mirrors only the tokens whose
 * CSS value is a **literal**, and `tokenParity.test.ts` parses `tokens.css` and fails
 * the build if any mirrored value stops matching.
 *
 * Tokens whose CSS value is an indirection (for example
 * `--surface-page: var(--paper-50)`) are intentionally NOT mirrored; antd derives
 * them from the primitive they point at.
 *
 * Font families are passed to antd as `var(--font-sans)` / `var(--font-mono)` so
 * there is exactly one definition of the type stack.
 */

/** Theme-agnostic primitives, declared once in `tokens.css`. */
export const primitiveTokens = {
  '--ink-900': '#0a0a0a',
  '--ink-800': '#18181b',
  '--ink-700': '#3f3f46',
  '--ink-600': '#52525b',
  '--ink-500': '#71717a',
  '--ink-400': '#a1a1aa',
  '--ink-300': '#d4d4d8',
  '--ink-200': '#e4e4e7',
  '--ink-100': '#f1f1f2',

  '--paper-0': '#ffffff',
  '--paper-50': '#fafafa',
  '--paper-100': '#f4f4f5',
  '--paper-200': '#ededee',

  '--line-100': '#f0f0f1',
  '--line-200': '#e4e4e7',
  '--line-300': '#d4d4d8',

  '--accent-400': '#2dd4bf',
  '--accent-500': '#14b8a6',
  '--accent-600': '#0f766e',
  '--accent-700': '#115e59',
  '--accent-900': '#042f2e',

  '--status-success': '#15803d',
  '--status-warning': '#b45309',
  '--status-danger': '#b91c1c',
  '--status-info': '#0369a1',

  '--radius-none': '0',
  '--radius-hair': '2px',
  '--radius-sm': '4px',
  '--radius-md': '6px',

  '--type-xs': '12px',
  '--type-sm': '13px',
  '--type-base': '14px',
  '--type-md': '16px',
  '--type-lg': '20px',
  '--type-xl': '28px',
  '--type-2xl': '40px',
  '--type-3xl': '64px',

  '--leading-base': '1.5',

  '--dur-fast': '140ms',
  '--dur-base': '240ms',
  '--dur-slow': '420ms',

  '--layout-sidebar': '264px',
  '--layout-header': '72px',
  '--layout-content-max': '1440px',
  '--layout-gutter': '24px',
} as const

/**
 * Dark-theme semantic literals, mirroring the `:root[data-theme='dark']` block.
 * Only the values whose CSS is a literal are listed.
 */
export const darkThemeLiterals = {
  '--surface-page': '#0a0a0a',
  '--surface-raised': '#121212',
  '--surface-sunken': '#050505',
  '--surface-interactive': '#161616',
  '--surface-hover': '#1c1c1c',
  '--surface-active': '#232323',
  '--text-primary': '#fafafa',
  '--text-secondary': '#d4d4d8',
  '--text-tertiary': '#a1a1aa',
  '--text-quaternary': '#71717a',
  '--border-hairline': '#262626',
  '--border-subtle': '#1a1a1a',
  '--border-strong': '#3f3f46',
} as const

/** Convert a CSS length such as `14px` into the number antd expects. */
export function px(value: string): number {
  return Number.parseFloat(value)
}

/** Convert a CSS duration such as `140ms` into the seconds string antd expects. */
export function seconds(value: string): string {
  const milliseconds = Number.parseFloat(value)
  return `${milliseconds / 1000}s`
}

/** Convert a hex colour plus alpha into an `rgba()` string. */
export function withAlpha(hex: string, alpha: number): string {
  const normalized = hex.replace('#', '')
  const red = Number.parseInt(normalized.slice(0, 2), 16)
  const green = Number.parseInt(normalized.slice(2, 4), 16)
  const blue = Number.parseInt(normalized.slice(4, 6), 16)
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`
}

export const tokens = primitiveTokens
export const darkTokens = darkThemeLiterals
