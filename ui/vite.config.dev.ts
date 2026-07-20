import { defineConfig } from 'vite'
import { resolve } from 'path'

// 开发服务器配置
export default defineConfig({
  // 开发服务器
  server: {
    port: 5173,
    open: true,
    // 允许访问静态文件
    fs: {
      allow: ['..'],
    },
  },
  
  // 解析别名
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  
  // CSS 处理
  css: {
    // 开发时不提取 CSS
    modules: {
      localsConvention: 'camelCase',
    },
  },
})
