/**
 * Button 组件类型定义
 */

export type ButtonVariant = 
  | 'primary' 
  | 'secondary' 
  | 'success' 
  | 'danger' 
  | 'warning' 
  | 'info' 
  | 'ghost' 
  | 'text'

export type ButtonSize = 'sm' | 'md' | 'lg'

export interface ButtonProps {
  /** 按钮内容 */
  children?: string
  /** 按钮文字 */
  text?: string
  /** 图标 */
  icon?: string
  /** 变体 */
  variant?: ButtonVariant
  /** 尺寸 */
  size?: ButtonSize
  /** 是否禁用 */
  disabled?: boolean
  /** 是否加载中 */
  loading?: boolean
  /** 是否块级按钮 */
  block?: boolean
  /** 点击事件 */
  onClick?: (event: MouseEvent) => void
  /** 自定义类名 */
  className?: string
}

/**
 * 生成 Button 类名
 */
export function getButtonClasses(props: ButtonProps): string {
  const {
    variant = 'primary',
    size = 'md',
    disabled = false,
    loading = false,
    block = false,
    className = '',
  } = props

  const classes = [
    'e-btn',
    `e-btn-${variant}`,
    size !== 'md' && `e-btn-${size}`,
    block && 'e-btn-block',
    loading && 'e-btn-loading',
    disabled && 'e-btn-disabled',
    className,
  ].filter(Boolean)

  return classes.join(' ')
}
