/**
 * Enforces the repository rule "no inline styles" (`CLAUDE.md`) as an executable
 * check instead of a convention.
 *
 * The codebase carried 101 inline `style={{ ... }}` objects, which is both a symptom
 * of having no design system and the reason theming could not be made consistent.
 * Files that are still being migrated are listed below; the list must shrink, and a
 * stale entry (a file that no longer violates) also fails so the list cannot rot.
 *
 * Genuine dynamic values (progress widths, chart geometry) must be written as CSS
 * custom properties — `style={{ '--progress': pct }}` — which is not matched here and
 * remains themeable.
 */
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob('/src/**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const INLINE_STYLE = /style=\{\{/

/** Files still awaiting migration. Remove an entry once the file is clean. */
const PENDING_MIGRATION = new Set<string>([
  'src/components/workbench/ViralityScorecard.tsx',
  'src/pages/AccountConfig.tsx',
  'src/pages/Login.tsx',
  'src/pages/ModelConfig.tsx',
  'src/pages/ReviewCenter.tsx',
  'src/pages/ScheduleManage.tsx',
  'src/pages/UserManage.tsx',
])

function normalise(path: string): string {
  return path.replace(/^\//, '')
}

const violations = Object.entries(sources)
  .filter(([path]) => !path.includes('__tests__') && !path.endsWith('.test.tsx'))
  .filter(([, code]) => INLINE_STYLE.test(code))
  .map(([path]) => normalise(path))

describe('no inline styles', () => {
  it('introduces no inline style objects outside the pending list', () => {
    const unexpected = violations.filter((path) => !PENDING_MIGRATION.has(path))
    expect(unexpected).toEqual([])
  })

  it('keeps the pending list honest (no stale entries)', () => {
    const stillViolating = new Set(violations)
    const stale = [...PENDING_MIGRATION].filter((path) => !stillViolating.has(path))
    expect(stale).toEqual([])
  })

  it('is making progress: fewer than 20 files remain', () => {
    // Ratchet: lower this bound as pages are migrated, and delete the list and the
    // compatibility layer in `variables.css` when it reaches zero.
    expect(PENDING_MIGRATION.size).toBeLessThan(20)
  })
})
