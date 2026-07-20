# Eyes UI 开发指南

## 开发模式 vs 发布模式

```
┌─────────────────────────────────────────────────────────────┐
│                        开发模式                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ui/src/ (源码)                                            │
│       ↓                                                     │
│   Vite Dev Server (HMR)                                     │
│       ↓                                                     │
│   浏览器即时预览                                             │
│                                                             │
│   特点：                                                     │
│   - 修改即生效，无需构建                                     │
│   - 支持热更新（HMR）                                        │
│   - 直接调试源码                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                        发布模式                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ui/src/ (源码)                                            │
│       ↓                                                     │
│   npm run build                                             │
│       ↓                                                     │
│   ui/dist/ (构建产物)                                        │
│       ↓                                                     │
│   复制到 eyes/static/eyes-ui/dist/                          │
│       ↓                                                     │
│   Docker 镜像打包                                            │
│                                                             │
│   特点：                                                     │
│   - Tree-shaking，体积最小                                   │
│   - 类型声明完整                                             │
│   - 适合生产环境                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 1. 启动 UI 开发服务器

```bash
cd ui

# 安装依赖（首次）
npm install

# 启动开发服务器
./dev.sh
# 或
npm run dev
```

打开 http://localhost:5173 预览组件。

### 2. Eyes 项目联调（可选）

```bash
# 创建符号链接
./link-dev.sh

# 然后在 eyes 模板中引用源码
# <link rel="stylesheet" href="/static/eyes-ui-dev/styles/base.css">
```

### 3. 修改组件

```
ui/src/
├── tokens/index.ts          # 修改颜色、间距等设计令牌
├── styles/base.css          # 修改基础样式
└── components/button/
    ├── button.css           # 修改按钮样式
    ├── Button.ts            # 修改按钮逻辑
    └── types.ts             # 修改按钮类型
```

修改后浏览器自动刷新（Vite HMR）。

### 4. 构建发布

```bash
# 构建 dist
./build.sh

# 构建并复制到 eyes/static
./build.sh --copy

# 重启 eyes Docker
cd ..
docker compose up -d
```

## 文件说明

| 文件 | 用途 |
|------|------|
| `index.html` | 组件预览页面（开发用） |
| `dev.sh` | 启动开发服务器 |
| `link-dev.sh` | 创建符号链接（联调用） |
| `build.sh` | 构建发布产物 |
| `src/tokens/` | 设计令牌（颜色、间距等） |
| `src/styles/` | 基础样式 |
| `src/components/` | 组件源码 |
| `dist/` | 构建产物（发布用） |

## 开发工作流

### 场景 1：只开发 UI 组件

```bash
cd ui
npm run dev          # 启动开发服务器
# 在浏览器预览和调试
npm run build        # 构建
```

### 场景 2：UI + Eyes 联调

```bash
cd ui
./link-dev.sh        # 创建符号链接
# 修改 UI 源码
# 刷新 eyes 页面查看效果
# 稳定后：
./build.sh --copy    # 构建并复制
cd .. && docker compose up -d  # 重启
./link-dev.sh -u     # 取消符号链接
```

### 场景 3：添加新组件

```bash
cd ui

# 1. 创建组件目录
mkdir -p src/components/new-component

# 2. 创建文件
touch src/components/new-component/NewComponent.ts
touch src/components/new-component/new-component.css
touch src/components/new-component/types.ts
touch src/components/new-component/index.ts
touch src/components/new-component/NewComponent.stories.ts

# 3. 开发组件
# ...

# 4. 在 index.html 中预览
# 5. 在 src/index.ts 中导出
# 6. 运行测试
npm test
```

## 设计令牌

所有设计决策通过令牌管理：

```ts
// src/tokens/index.ts
export const globalTokens = {
  colors: { ... },    // 颜色
  spacing: { ... },   // 间距
  radius: { ... },    // 圆角
  fontSize: { ... },  // 字号
}
```

修改令牌后，所有组件自动更新。

## 测试

```bash
# 运行测试
npm test

# 运行测试并生成覆盖率
npm run test:coverage

# 启动测试 UI
npm run test:ui
```

## Storybook 文档

```bash
# 启动 Storybook
npm run storybook

# 构建静态文档
npm run storybook:build
```

## 常见问题

### Q: 如何在 eyes 中使用新组件？

A: 开发阶段使用符号链接：
```bash
cd ui && ./link-dev.sh
```

然后在 eyes 模板中引用：
```html
<link rel="stylesheet" href="/static/eyes-ui-dev/components/new-component/new-component.css">
```

### Q: 如何修改主题颜色？

A: 编辑 `src/tokens/index.ts` 中的 `semanticTokens.dark`。

### Q: 如何添加亮色主题？

A: 在 `src/tokens/index.ts` 中实现 `semanticTokens.light`，然后在 CSS 变量生成函数中添加主题切换逻辑。

### Q: 构建后如何更新 eyes？

A: 
```bash
cd ui && ./build.sh --copy
cd .. && docker compose up -d
```
