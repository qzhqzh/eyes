/**
 * Button 组件测试
 */

import { describe, it, expect } from 'vitest'
import { Button, getButtonClasses } from '../src/components/button'

describe('Button', () => {
  it('renders with default props', () => {
    const html = Button({ text: 'Click' })
    expect(html).toContain('e-btn')
    expect(html).toContain('e-btn-primary')
    expect(html).toContain('Click')
  })

  it('renders with variant', () => {
    const html = Button({ text: 'Test', variant: 'danger' })
    expect(html).toContain('e-btn-danger')
  })

  it('renders with size', () => {
    const html = Button({ text: 'Test', size: 'lg' })
    expect(html).toContain('e-btn-lg')
  })

  it('renders disabled state', () => {
    const html = Button({ text: 'Test', disabled: true })
    expect(html).toContain('disabled')
    expect(html).toContain('aria-disabled="true"')
  })

  it('renders loading state', () => {
    const html = Button({ text: 'Test', loading: true })
    expect(html).toContain('e-btn-loading')
    expect(html).toContain('aria-busy="true"')
  })

  it('renders block button', () => {
    const html = Button({ text: 'Test', block: true })
    expect(html).toContain('e-btn-block')
  })

  it('renders icon', () => {
    const html = Button({ text: 'Test', icon: '🚀' })
    expect(html).toContain('🚀')
  })
})

describe('getButtonClasses', () => {
  it('returns default classes', () => {
    const classes = getButtonClasses({})
    expect(classes).toContain('e-btn')
    expect(classes).toContain('e-btn-primary')
    expect(classes).toContain('e-btn-md')
  })

  it('includes variant class', () => {
    const classes = getButtonClasses({ variant: 'ghost' })
    expect(classes).toContain('e-btn-ghost')
  })

  it('includes size class', () => {
    const classes = getButtonClasses({ size: 'sm' })
    expect(classes).toContain('e-btn-sm')
  })

  it('includes disabled class', () => {
    const classes = getButtonClasses({ disabled: true })
    expect(classes).toContain('e-btn-disabled')
  })

  it('includes loading class', () => {
    const classes = getButtonClasses({ loading: true })
    expect(classes).toContain('e-btn-loading')
  })

  it('includes block class', () => {
    const classes = getButtonClasses({ block: true })
    expect(classes).toContain('e-btn-block')
  })

  it('includes custom class', () => {
    const classes = getButtonClasses({ className: 'my-class' })
    expect(classes).toContain('my-class')
  })
})
