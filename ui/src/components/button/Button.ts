/**
 * Button 按钮组件
 * 
 * @example
 * ```ts
 * import { Button } from '@eyes-ui/core'
 * 
 * const btn = Button({ text: '点击', variant: 'primary' })
 * document.body.innerHTML = btn
 * ```
 */

import { type ButtonProps, getButtonClasses } from './types'
import './button.css'

/**
 * 渲染 Button HTML
 */
export function Button(props: ButtonProps): string {
  const {
    children,
    text = '',
    icon = '',
    disabled = false,
    loading = false,
    onClick,
  } = props

  const classes = getButtonClasses(props)
  const content = children || text

  return `
    <button 
      class="${classes}"
      ${disabled ? 'disabled' : ''}
      ${onClick ? `onclick="(${onClick.toString()})(event)"` : ''}
      type="button"
      role="button"
      aria-disabled="${disabled}"
      aria-busy="${loading}"
    >
      ${loading ? '<span class="e-btn-spinner" aria-hidden="true"></span>' : ''}
      ${icon && !loading ? `<span class="e-btn-icon-inner" aria-hidden="true">${icon}</span>` : ''}
      ${content ? `<span>${content}</span>` : ''}
    </button>
  `
}

/**
 * 渲染图标按钮
 */
export function IconButton(props: ButtonProps & { 'aria-label': string }): string {
  return Button({ ...props, children: props.icon })
}

// 导出类型
export type { ButtonProps }
export { getButtonClasses }
