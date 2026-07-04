/**
 * Eyes UI CSS Variables Generator
 * 
 * 从设计令牌生成 CSS 变量
 */

import { semanticTokens, globalTokens } from '../tokens'

/**
 * 生成 CSS 变量字符串
 */
export function generateCSSVariables(): string {
  const theme = semanticTokens.dark // 当前使用深色主题

  return `
/* =====================================================
   Eyes UI — Design Tokens (Auto-generated)
   
   ⚠️ 请勿手动修改此文件
   运行 npm run build:tokens 重新生成
   ===================================================== */

:root {
  /* ========== 主色 ========== */
  --eyes-primary: ${theme.primary};
  --eyes-primary-hover: ${theme['primary-hover']};
  --eyes-primary-light: ${theme['primary-light']};
  --eyes-primary-text: #ffffff;

  /* ========== 语义色 ========== */
  --eyes-success: ${theme.success};
  --eyes-success-hover: ${theme['success-hover']};
  --eyes-success-light: ${theme['success-light']};

  --eyes-warning: ${theme.warning};
  --eyes-warning-hover: ${theme['warning-hover']};
  --eyes-warning-light: ${theme['warning-light']};

  --eyes-danger: ${theme.danger};
  --eyes-danger-hover: ${theme['danger-hover']};
  --eyes-danger-light: ${theme['danger-light']};

  /* ========== 背景色 ========== */
  --eyes-bg-page: ${theme['bg-page']};
  --eyes-bg-sidebar: ${theme['bg-sidebar']};
  --eyes-bg-card: ${theme['bg-card']};
  --eyes-bg-card-hover: ${theme['bg-card-hover']};
  --eyes-bg-input: ${theme['bg-input']};
  --eyes-bg-mask: ${theme['bg-mask']};

  /* ========== 文字颜色 ========== */
  --eyes-text-primary: ${theme['text-primary']};
  --eyes-text-secondary: ${theme['text-secondary']};
  --eyes-text-muted: ${theme['text-muted']};
  --eyes-text-disabled: ${theme['text-disabled']};
  --eyes-text-placeholder: ${theme['text-placeholder']};

  /* ========== 边框 ========== */
  --eyes-border: ${theme.border};
  --eyes-border-hover: ${theme['border-hover']};
  --eyes-border-focus: ${theme['border-focus']};

  /* ========== 间距 ========== */
  --eyes-spacing: ${globalTokens.spacing[3.5]};
  --eyes-spacing-lg: ${globalTokens.spacing[5]};
  --eyes-spacing-sm: ${globalTokens.spacing[2.5]};
  --eyes-spacing-xs: ${globalTokens.spacing[1.5]};
  --eyes-spacing-2xs: ${globalTokens.spacing[1]};

  /* ========== 圆角 ========== */
  --eyes-radius: ${globalTokens.radius.md};
  --eyes-radius-sm: ${globalTokens.radius.sm};
  --eyes-radius-lg: ${globalTokens.radius.lg};
  --eyes-radius-xl: ${globalTokens.radius.xl};
  --eyes-radius-full: ${globalTokens.radius.full};

  /* ========== 字体 ========== */
  --eyes-font-family: ${globalTokens.fontFamily.sans};
  --eyes-font-size-xs: ${globalTokens.fontSize.xs[0]};
  --eyes-font-size-sm: ${globalTokens.fontSize.sm[0]};
  --eyes-font-size-base: ${globalTokens.fontSize.base[0]};
  --eyes-font-size-md: ${globalTokens.fontSize.md[0]};
  --eyes-font-size-lg: ${globalTokens.fontSize.lg[0]};
  --eyes-font-size-xl: ${globalTokens.fontSize.xl[0]};
  --eyes-font-size-2xl: ${globalTokens.fontSize['2xl'][0]};
  --eyes-font-size-3xl: ${globalTokens.fontSize['3xl'][0]};

  --eyes-font-weight-normal: ${globalTokens.fontWeight.normal};
  --eyes-font-weight-medium: ${globalTokens.fontWeight.medium};
  --eyes-font-weight-semibold: ${globalTokens.fontWeight.semibold};
  --eyes-font-weight-bold: ${globalTokens.fontWeight.bold};

  --eyes-line-height-tight: 1.2;
  --eyes-line-height-normal: 1.5;
  --eyes-line-height-relaxed: 1.75;

  /* ========== 阴影 ========== */
  --eyes-shadow-sm: ${globalTokens.boxShadow.sm};
  --eyes-shadow: ${globalTokens.boxShadow.DEFAULT};
  --eyes-shadow-lg: ${globalTokens.boxShadow.lg};
  --eyes-shadow-xl: ${globalTokens.boxShadow.xl};

  /* ========== 动画 ========== */
  --eyes-transition-fast: ${globalTokens.transition.fast};
  --eyes-transition: ${globalTokens.transition.DEFAULT};
  --eyes-transition-slow: ${globalTokens.transition.slow};
}
`.trim()
}
