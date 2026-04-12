import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'

test('renders a simple element in jsdom', () => {
  render(<div>brand studio smoke</div>)

  expect(screen.getByText('brand studio smoke')).toBeInTheDocument()
})
