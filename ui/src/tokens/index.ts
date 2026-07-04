/**
 * Eyes UI Design Tokens
 * 
 * 设计令牌是设计系统的基础，定义了颜色、间距、字体等设计决策。
 * 采用三层结构：Global → Alias → Component
 */

// ============================================================
// Global Tokens（全局令牌）
// ============================================================

export const globalTokens = {
  // 颜色
  colors: {
    // 原色
    indigo: {
      50: '#eef2ff',
      100: '#e0e7ff',
      200: '#c7d2fe',
      300: '#a5b4fc',
      400: '#818cf8',
      500: '#6366f1',
      600: '#4f46e5',
      700: '#4338ca',
      800: '#3730a3',
      900: '#312e81',
    },
    emerald: {
      50: '#ecfdf5',
      100: '#d1fae5',
      200: '#a7f3d0',
      300: '#6ee7b7',
      400: '#34d399',
      500: '#10b981',
      600: '#059669',
      700: '#047857',
      800: '#065f46',
      900: '#064e3b',
    },
    amber: {
      50: '#fffbeb',
      100: '#fef3c7',
      200: '#fde68a',
      300: '#fcd34d',
      400: '#fbbf24',
      500: '#f59e0b',
      600: '#d97706',
      700: '#b45309',
      800: '#92400e',
      900: '#78350f',
    },
    rose: {
      50: '#fff1f2',
      100: '#ffe4e6',
      200: '#fecdd3',
      300: '#fda4af',
      400: '#fb7185',
      500: '#f43f5e',
      600: '#e11d48',
      700: '#be123c',
      800: '#9f1239',
      900: '#881337',
    },
    slate: {
      50: '#f8fafc',
      100: '#f1f5f9',
      200: '#e2e8f0',
      300: '#cbd5e1',
      400: '#94a3b8',
      500: '#64748b',
      600: '#475569',
      700: '#334155',
      800: '#1e293b',
      900: '#0f172a',
      950: '#020617',
    },
  },

  // 间距（4px 基准）
  spacing: {
    0: '0px',
    0.5: '2px',
    1: '4px',
    1.5: '6px',
    2: '8px',
    2.5: '10px',
    3: '12px',
    3.5: '14px',
    4: '16px',
    5: '20px',
    6: '24px',
    7: '28px',
    8: '32px',
    9: '36px',
    10: '40px',
    12: '48px',
    14: '56px',
    16: '64px',
  },

  // 圆角
  radius: {
    none: '0px',
    sm: '4px',
    DEFAULT: '6px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    '2xl': '20px',
    '3xl': '24px',
    full: '9999px',
  },

  // 字体
  fontFamily: {
    sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", "Noto Sans SC", sans-serif',
    mono: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
  },

  // 字号
  fontSize: {
    xs: ['11px', { lineHeight: '1.4' }],
    sm: ['12px', { lineHeight: '1.4' }],
    base: ['13px', { lineHeight: '1.5' }],
    md: ['14px', { lineHeight: '1.5' }],
    lg: ['16px', { lineHeight: '1.5' }],
    xl: ['20px', { lineHeight: '1.4' }],
    '2xl': ['24px', { lineHeight: '1.3' }],
    '3xl': ['28px', { lineHeight: '1.2' }],
    '4xl': ['32px', { lineHeight: '1.2' }],
  },

  // 字重
  fontWeight: {
    normal: '400',
    medium: '500',
    semibold: '600',
    bold: '700',
  },

  // 阴影
  boxShadow: {
    sm: '0 1px 2px 0 rgb(0 0 0 / 0.3)',
    DEFAULT: '0 1px 3px 0 rgb(0 0 0 / 0.3), 0 1px 2px -1px rgb(0 0 0 / 0.3)',
    md: '0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3)',
    lg: '0 10px 15px -3px rgb(0 0 0 / 0.4), 0 4px 6px -4px rgb(0 0 0 / 0.4)',
    xl: '0 20px 25px -5px rgb(0 0 0 / 0.5), 0 8px 10px -6px rgb(0 0 0 / 0.5)',
  },

  // 动画
  transition: {
    fast: '150ms ease',
    DEFAULT: '200ms ease',
    slow: '300ms ease',
    slower: '500ms ease',
  },
} as const

// ============================================================
// Semantic Tokens（语义令牌）
// ============================================================

export const semanticTokens = {
  // 浅色主题（预留）
  light: {
    // ...
  },

  // 深色主题（当前使用）
  dark: {
    // 主色
    primary: globalTokens.colors.indigo[500],
    'primary-hover': globalTokens.colors.indigo[600],
    'primary-light': 'rgba(99, 102, 241, 0.1)',

    // 语义色
    success: globalTokens.colors.emerald[500],
    'success-hover': globalTokens.colors.emerald[600],
    'success-light': 'rgba(16, 185, 129, 0.1)',

    warning: globalTokens.colors.amber[500],
    'warning-hover': globalTokens.colors.amber[600],
    'warning-light': 'rgba(245, 158, 11, 0.1)',

    danger: '#ef4444',
    'danger-hover': '#dc2626',
    'danger-light': 'rgba(239, 68, 68, 0.1)',

    // 背景色
    'bg-page': '#0f0f12',
    'bg-sidebar': '#1a1a1f',
    'bg-card': '#1e1e24',
    'bg-card-hover': '#26262e',
    'bg-input': '#2a2a33',
    'bg-mask': 'rgba(0, 0, 0, 0.6)',

    // 文字颜色
    'text-primary': globalTokens.colors.slate[50],
    'text-secondary': globalTokens.colors.slate[300],
    'text-muted': globalTokens.colors.slate[500],
    'text-disabled': globalTokens.colors.slate[600],
    'text-placeholder': globalTokens.colors.slate[600],

    // 边框
    border: '#2d2d35',
    'border-hover': '#3d3d47',
    'border-focus': 'var(--eyes-primary)',
  },
} as const

// ============================================================
// Component Tokens（组件令牌）
// ============================================================

export const componentTokens = {
  button: {
    height: {
      sm: '28px',
      md: '36px',
      lg: '44px',
    },
    padding: {
      sm: '6px 10px',
      md: '10px 14px',
      lg: '14px 20px',
    },
    fontSize: {
      sm: globalTokens.fontSize.base,
      md: globalTokens.fontSize.md,
      lg: globalTokens.fontSize.lg,
    },
  },
  input: {
    height: {
      sm: '28px',
      md: '36px',
      lg: '44px',
    },
    padding: {
      sm: '6px 10px',
      md: '10px 14px',
      lg: '14px 20px',
    },
  },
  card: {
    padding: '14px',
    radius: globalTokens.radius.md,
  },
  modal: {
    width: {
      sm: '400px',
      md: '520px',
      lg: '720px',
    },
    radius: globalTokens.radius.xl,
  },
  badge: {
    padding: '4px 10px',
    radius: globalTokens.radius.sm,
  },
} as const

// ============================================================
// 导出类型
// ============================================================

export type GlobalTokens = typeof globalTokens
export type SemanticTokens = typeof semanticTokens
export type ComponentTokens = typeof componentTokens
export type Theme = 'light' | 'dark'
