import { describe, expect, it } from 'vitest'

/**
 * Guard: no page or component may render a *dynamic* string directly as a heading or
 * paragraph.
 *
 * The bug this prevents: `ArticleManage` rendered the full article title and a summary of up
 * to 200 characters straight into `<h2>`/`<p>`. The grid column was already correct
 * (`minmax(0, 1fr)` plus `min-width: 0`), but nothing clamped the text itself, so a long
 * summary made the card arbitrarily tall and visibly distorted the surrounding grid. The same
 * pattern appeared in `TopicCenter`, `TaskDetail`, `ViralityScorecard` and `StatusRail`.
 *
 * `TruncatedText` is the fix: it clamps to N lines, sets the `min-width: 0` that makes the
 * ellipsis actually appear inside a flex/grid child, and keeps the full value in a native
 * `title` tooltip.
 *
 * Static literals like `<p>确认后会将当前文章渲染为微信样式 HTML…</p>` are fine — their length
 * is known at review time and cannot change with API data.
 */
const SOURCES = import.meta.glob('/src/**/*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>

/** Matches `<h1>{expr}` … `<p>{expr}` — a dynamic value rendered with no clamp wrapper. */
const BARE_DYNAMIC_TEXT = /<(h[1-3]|p)>\s*\{/g

/**
 * Files allowed to keep a bare dynamic heading/paragraph.
 *
 * `WorkbenchShell` prints navigation metadata (`contextTitle` / `contextDescription`) that is
 * authored once in the nav table, not fetched — it cannot grow with data.
 */
const ALLOWED = new Set<string>(['/src/components/workbench/WorkbenchShell.tsx'])

function fileOf(path: string): string {
  return path.replace(/^.*\/src\//, '/src/')
}

describe('long text cannot break a layout', () => {
  it('finds source files to scan', () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(20)
  })

  it('has no unclamped dynamic heading or paragraph outside the allowlist', () => {
    const offenders: string[] = []

    for (const [path, source] of Object.entries(SOURCES)) {
      const relative = fileOf(path)
      if (ALLOWED.has(relative)) {
        continue
      }
      // Ignore comments so documentation examples do not trip the guard.
      const withoutComments = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')
      const matches = withoutComments.match(BARE_DYNAMIC_TEXT)
      if (matches) {
        offenders.push(`${relative}: ${matches.join(', ')}`)
      }
    }

    expect(offenders, `wrap these in <TruncatedText>:\n${offenders.join('\n')}`).toEqual([])
  })

  it('keeps the allowlist honest by still matching what it excuses', () => {
    // If WorkbenchShell stops rendering bare dynamic text, the entry above should be removed.
    const shell = SOURCES['/src/components/workbench/WorkbenchShell.tsx']
    expect(shell).toBeTruthy()
    expect(shell.match(BARE_DYNAMIC_TEXT)).toBeTruthy()
  })

  it('routes the long-text surfaces through TruncatedText', () => {
    const expectations: Array<[string, string]> = [
      ['/src/pages/ArticleManage.tsx', 'article summary'],
      ['/src/pages/TopicCenter.tsx', 'topic title'],
      ['/src/pages/TaskDetail.tsx', 'article title'],
      ['/src/components/workbench/ViralityScorecard.tsx', 'LLM-generated promise/tension'],
      ['/src/components/workbench/StatusRail.tsx', 'step description'],
    ]

    for (const [path, label] of expectations) {
      const source = SOURCES[path]
      expect(source, `${path} not found`).toBeTruthy()
      expect(source, `${label} is not clamped`).toContain('TruncatedText')
    }
  })
})
