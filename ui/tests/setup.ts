/**
 * 测试设置文件
 */

// 模拟浏览器 API
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// 清理 DOM
afterEach(() => {
  document.body.innerHTML = ''
})
