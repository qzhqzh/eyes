import type { Preview } from '@storybook/web-components'

// 导入样式
import '../src/styles/base.css'
import '../src/components/button/button.css'

// 导入并应用设计令牌
import { generateCSSVariables } from '../src/tokens/css-variables'

// 注入 CSS 变量
const style = document.createElement('style')
style.textContent = generateCSSVariables()
document.head.appendChild(style)

const preview: Preview = {
  parameters: {
    actions: { argTypesRegex: '^on[A-Z].*' },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    backgrounds: {
      default: 'dark',
      values: [
        { name: 'dark', value: '#0f0f12' },
        { name: 'light', value: '#ffffff' },
      ],
    },
  },
}

export default preview
