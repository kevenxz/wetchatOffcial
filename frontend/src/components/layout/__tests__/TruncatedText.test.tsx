import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TruncatedText from '../TruncatedText'
import styles from '../layout.module.css'

const LONG_SUMMARY =
  '这是一段很长的文章摘要，用来验证过长的文本不会把卡片撑破。'.repeat(6)

describe('TruncatedText', () => {
  it('renders the text and clamps it to one line by default', () => {
    render(<TruncatedText>{LONG_SUMMARY}</TruncatedText>)

    const node = screen.getByText(LONG_SUMMARY)
    expect(node.className).toContain(styles.clamp1)
    expect(node.className).toContain(styles.truncated)
  })

  it('applies the requested line clamp', () => {
    render(
      <TruncatedText lines={3}>{LONG_SUMMARY}</TruncatedText>,
    )

    expect(screen.getByText(LONG_SUMMARY).className).toContain(styles.clamp3)
  })

  it('exposes the full text as a native tooltip so truncation loses nothing', () => {
    render(<TruncatedText lines={2}>{LONG_SUMMARY}</TruncatedText>)

    // The whole string stays reachable even though only two lines are shown.
    expect(screen.getByText(LONG_SUMMARY)).toHaveAttribute('title', LONG_SUMMARY)
  })

  it('lets the caller override the tooltip', () => {
    render(
      <TruncatedText title="自定义提示">{LONG_SUMMARY}</TruncatedText>,
    )

    expect(screen.getByText(LONG_SUMMARY)).toHaveAttribute('title', '自定义提示')
  })

  it('renders the requested element so heading semantics survive', () => {
    render(
      <TruncatedText as="h2" lines={2}>
        标题
      </TruncatedText>,
    )

    const heading = screen.getByRole('heading', { level: 2 })
    expect(heading).toHaveTextContent('标题')
    expect(heading.className).toContain(styles.clamp2)
  })

  it('omits the tooltip for non-string children', () => {
    render(
      <TruncatedText>
        <span>结构化内容</span>
      </TruncatedText>,
    )

    const node = screen.getByText('结构化内容').parentElement
    expect(node).not.toHaveAttribute('title')
  })

  it('keeps caller classes alongside the clamp', () => {
    render(<TruncatedText className="custom-class">{LONG_SUMMARY}</TruncatedText>)

    const node = screen.getByText(LONG_SUMMARY)
    expect(node.className).toContain('custom-class')
    expect(node.className).toContain(styles.truncated)
  })
})

describe('clamp styles', () => {
  it('defines a clamp class for every supported line count', () => {
    for (const key of ['clamp1', 'clamp2', 'clamp3', 'clamp4'] as const) {
      expect(styles[key]).toBeTruthy()
    }
  })
})
