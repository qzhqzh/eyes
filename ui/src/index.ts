/**
 * Eyes UI — 主入口
 * 
 * @example
 * ```ts
 * import { Button, Card, toast } from '@eyes-ui/core'
 * import '@eyes-ui/core/styles'
 * ```
 */

// ============================================================
// 组件导出
// ============================================================

// Button
export { Button, IconButton } from './components/button'
export type { ButtonProps, ButtonVariant, ButtonSize } from './components/button'

// ============================================================
// 工具函数导出
// ============================================================

export { cn, uniqueId, delay, debounce, throttle, formatNumber } from './utils'

// ============================================================
// 设计令牌导出
// ============================================================

export { globalTokens, semanticTokens, componentTokens } from './tokens'
export type { GlobalTokens, SemanticTokens, ComponentTokens, Theme } from './tokens'

// ============================================================
// 版本信息
// ============================================================

export const VERSION = '1.0.0'
export const NAME = '@eyes-ui/core'
