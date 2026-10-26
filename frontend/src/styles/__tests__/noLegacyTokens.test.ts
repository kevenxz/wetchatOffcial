/**
 * Tracks the migration away from the legacy token names.
 *
 * `variables.css` is a temporary compatibility layer that aliases the old
 * `--app-*` / `--color-*` names onto the semantic tokens in `tokens.css`. It must be
 * deleted once nothing references those names, otherwise the design system has two
 * vocabularies forever. This test makes that progress enforceable: new code may not
 * use legacy names, and the pending list must not rot.
 */
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob('/src/**/*.{ts,tsx,css}', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const LEGACY_PATTERNS: RegExp[] = [
  /var\(--app-[\w-]+\)/,
  /var\(--color-(?:primary|success|warning|error|info)(?:-[\w-]+)?\)/,
  /var\(--color-gray-\d+\)/,
  /var\(--bg-[\w-]+\)/,
  /var\(--border-color[\w-]*\)/,
  /var\(--border-radius[\w-]*\)/,
  /var\(--space-(?:xs|sm|md|lg|xl|2xl|3xl)\)/,
  /var\(--font-family-[\w-]+\)/,
  /var\(--font-(?:xs|sm|base|lg|xl|2xl|3xl)\)/,
  /var\(--line-height-[\w-]+\)/,
  /var\(--font-weight-[\w-]+\)/,
  /var\(--shadow-(?:sm|md|lg)\)/,
  /var\(--transition-(?:fast|base|slow)\)/,
  /var\(--(?:sider-width|sider-collapsed-width|header-height|content-padding)\)/,
  /var\(--text-disabled\)/,
]

/** Files still referencing legacy names. Remove an entry once the file is clean. */
const PENDING_MIGRATION = new Set<string>([
  'src/components/topics/TopicScoreCard.module.css',
  'src/components/workbench/AssetList.module.css',
  'src/components/workbench/HeroPanel.module.css',
  'src/components/workbench/SignalCard.module.css',
  'src/components/workbench/StatusRail.module.css',
  'src/components/workbench/ThemeModeSwitch.module.css',
  'src/components/workbench/ViralityScorecard.module.css',
  'src/pages/AccountConfig.tsx',
  'src/pages/ArticleManage.module.css',
  'src/pages/Login.module.css',
  'src/pages/ModelConfig.tsx',
  // The legacy `.backstage-*` scaffolding intentionally stays on the aliases until
  // those pages are re-composed with the layout primitives.
  'src/styles/global.css',
])

function usesLegacyToken(code: string): boolean {
  return LEGACY_PATTERNS.some((pattern) => pattern.test(code))
}

const violations = Object.entries(sources)
  .filter(([path]) => !path.includes('__tests__'))
  .filter(([path]) => !path.endsWith('variables.css') && !path.endsWith('tokens.css'))
  .filter(([, code]) => usesLegacyToken(code))
  .map(([path]) => path.replace(/^\//, ''))

describe('legacy design tokens', () => {
  it('are not used by any file outside the pending list', () => {
    const unexpected = violations.filter((path) => !PENDING_MIGRATION.has(path))
    expect(unexpected).toEqual([])
  })

  it('keeps the pending list honest (no stale entries)', () => {
    const stillUsing = new Set(violations)
    const stale = [...PENDING_MIGRATION].filter((path) => !stillUsing.has(path))
    expect(stale).toEqual([])
  })

  it('leaves the new shell, landing page and primitives fully migrated', () => {
    const migrated = [
      'src/components/workbench/WorkbenchShell.tsx',
      'src/components/workbench/WorkbenchShell.module.css',
      'src/pages/Landing.tsx',
      'src/pages/Landing.module.css',
      'src/components/brand/BrandMark.tsx',
      'src/components/layout/layout.module.css',
      'src/motion/motion.module.css',
      'src/theme.ts',
    ]

    expect(migrated.filter((path) => violations.includes(path))).toEqual([])
  })
})
