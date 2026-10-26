/**
 * Guards the design token layer against drift.
 *
 * The token values live in CSS because that is what components consume, but antd
 * needs a subset of the same values in JavaScript. Two hand-maintained copies of a
 * palette always drift — that is exactly how the documented brand colour
 * (`#1677FF`) and the implemented one (`#0f766e`) ended up disagreeing. This test
 * parses `tokens.css` and fails if `tokens.ts` stops matching it.
 */
import { describe, expect, it } from 'vitest'
import { darkThemeLiterals, primitiveTokens } from '../tokens'
// `?raw` keeps this independent of the working directory and of `import.meta.url`,
// which Vitest rewrites to an http:// URL.
import css from '../tokens.css?raw'

/** Read one rule block into a `--name` → value map. */
function readBlock(selector: string): Record<string, string> {
  const start = css.indexOf(selector)
  if (start < 0) {
    throw new Error(`token block not found: ${selector}`)
  }
  const open = css.indexOf('{', start)
  const close = css.indexOf('}', open)
  const body = css.slice(open + 1, close)

  const declarations: Record<string, string> = {}
  for (const line of body.split('\n')) {
    const match = line.match(/^\s*(--[\w-]+)\s*:\s*(.+?);\s*$/)
    if (match) {
      declarations[match[1]] = match[2].trim()
    }
  }
  return declarations
}

const rootBlock = readBlock(':root {')
const darkBlock = readBlock(":root[data-theme='dark']")

describe('design token parity', () => {
  it.each(Object.entries(primitiveTokens))('primitive %s matches tokens.css', (name, value) => {
    expect(rootBlock[name]).toBe(value)
  })

  it.each(Object.entries(darkThemeLiterals))('dark %s matches the dark block', (name, value) => {
    expect(darkBlock[name]).toBe(value)
  })

  it('declares every mirrored token in the CSS at all', () => {
    const missing = [...Object.keys(primitiveTokens), ...Object.keys(darkThemeLiterals)].filter(
      (name) => !(name in rootBlock) && !(name in darkBlock),
    )
    expect(missing).toEqual([])
  })

  it('defines each primitive exactly once', () => {
    // The previous token file duplicated the whole light palette between `:root`
    // and `:root[data-theme='light']`, so every colour change had to be made twice.
    const duplicated = Object.keys(primitiveTokens).filter((name) => {
      const occurrences = css.match(new RegExp(`^\\s*${name}\\s*:`, 'gm')) ?? []
      return occurrences.length !== 1
    })
    expect(duplicated).toEqual([])
  })

  it('keeps the dark theme to the semantic layer only', () => {
    const semanticPrefixes = [
      '--surface-',
      '--text-',
      '--border-',
      '--accent',
      '--status-',
      '--focus-',
      '--elevation-',
    ]
    const offenders = Object.keys(darkBlock).filter(
      (name) => name !== '--grid-line' && !semanticPrefixes.some((prefix) => name.startsWith(prefix)),
    )
    expect(offenders).toEqual([])
  })

  it('does not redefine primitives inside the dark theme', () => {
    const leaked = Object.keys(primitiveTokens).filter((name) => name in darkBlock)
    expect(leaked).toEqual([])
  })
})
