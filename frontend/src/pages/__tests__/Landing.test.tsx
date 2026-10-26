/**
 * The landing page is the only public surface, so these assertions cover the two
 * things that matter: it renders without authentication, and its CTA leads into the
 * console.
 */
import { screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import LandingPage from '@/pages/Landing'
import { renderWithRouter } from '@/test/renderWithRouter'

test('renders the public landing page without authentication', () => {
  renderWithRouter(<LandingPage />, { route: '/' })

  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('从热点到草稿箱')
  expect(screen.getByText('微信公众号内容生产自动化')).toBeInTheDocument()
})

test('offers a way into the console', () => {
  renderWithRouter(<LandingPage />, { route: '/' })

  const ctas = screen.getAllByRole('link', { name: '进入控制台' })
  expect(ctas.length).toBeGreaterThan(0)
  expect(ctas[0]).toHaveAttribute('href', '/login')
})

test('describes the real pipeline stages', () => {
  renderWithRouter(<LandingPage />, { route: '/' })

  for (const stage of ['捕获热点', '先读原文', '过滤来源', '决定结构', '推送发布']) {
    expect(screen.getByText(stage)).toBeInTheDocument()
  }
})

test('shows the capability and metric blocks', () => {
  renderWithRouter(<LandingPage />, { route: '/' })

  expect(screen.getByText('热点原文优先')).toBeInTheDocument()
  expect(screen.getByText('来源过滤')).toBeInTheDocument()
  expect(screen.getByText('动态文章结构')).toBeInTheDocument()

  // Counter values resolve immediately when they cannot animate (jsdom).
  expect(screen.getByText('工作流节点')).toBeInTheDocument()
  expect(screen.getByText('23')).toBeInTheDocument()
})
