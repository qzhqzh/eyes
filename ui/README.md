# Eyes UI 组件库

现代化深色主题组件库，专为监控仪表盘设计。

## 两种模式

### 开发模式（推荐开发时使用）

```bash
cd ui

# 安装依赖
npm install

# 启动开发服务器
./dev.sh

# 打开浏览器预览
# http://localhost:5173
```

**特点：**
- ✅ 修改即时生效（HMR）
- ✅ 无需构建
- ✅ 直接调试源码

### 发布模式（给其他项目用）

```bash
cd ui

# 构建
./build.sh

# 构建并复制到 eyes/static
./build.sh --copy
```

**特点：**
- ✅ Tree-shaking，体积小
- ✅ 完整类型声明
- ✅ 适合生产环境

## 开发流程

```
┌─────────────────────────────────────────────────────────┐
│  1. 开发                                                │
│     cd ui && ./dev.sh                                   │
│     浏览器打开 http://localhost:5173                     │
│     修改 src/ 下的文件                                   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  2. 联调（可选）                                        │
│     ./link-dev.sh                                       │
│     eyes 项目直接引用 ui 源码                            │
│     刷新 eyes 页面查看效果                               │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  3. 构建                                                │
│     ./build.sh --copy                                   │
│     复制到 eyes/static/eyes-ui/dist/                    │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  4. 部署                                                │
│     cd .. && docker compose up -d                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## 目录结构

```
ui/
├── src/                    # 源码（开发时修改这里）
│   ├── tokens/             # 设计令牌
│   ├── styles/             # 基础样式
│   ├── components/         # 组件
│   └── utils/              # 工具函数
├── dist/                   # 构建产物（发布用）
├── tests/                  # 测试
├── .storybook/             # Storybook 文档
├── index.html              # 组件预览（开发用）
├── dev.sh                  # 启动开发服务器
├── link-dev.sh             # 创建符号链接
├── build.sh                # 构建脚本
└── package.json
```

## 命令

| 命令 | 说明 |
|------|------|
| `npm run dev` | 启动开发服务器 |
| `npm run build` | 构建 dist |
| `npm test` | 运行测试 |
| `npm run storybook` | 启动 Storybook |
| `./dev.sh` | 启动开发服务器（快捷） |
| `./dev.sh eyes` | 启动并代理到 eyes |
| `./link-dev.sh` | 创建符号链接 |
| `./link-dev.sh -u` | 取消符号链接 |
| `./build.sh` | 构建 |
| `./build.sh --copy` | 构建并复制到 eyes |

## 组件列表

| 组件 | 状态 | 说明 |
|------|------|------|
| Button | ✅ | 按钮 |
| Card | 📋 | 卡片（待开发） |
| Badge | 📋 | 徽章（待开发） |
| Input | 📋 | 输入框（待开发） |
| Select | 📋 | 选择器（待开发） |
| Modal | 📋 | 弹窗（待开发） |
| Toast | 📋 | 提示（待开发） |
| Table | 📋 | 表格（待开发） |
| Pagination | 📋 | 分页（待开发） |
| List | 📋 | 列表（待开发） |

## 设计令牌

所有设计决策通过令牌管理，修改令牌后所有组件自动更新：

```ts
// src/tokens/index.ts
export const semanticTokens = {
  dark: {
    primary: '#6366f1',      // 主色
    success: '#10b981',      // 成功色
    warning: '#f59e0b',      // 警告色
    danger: '#ef4444',       // 危险色
    'bg-page': '#0f0f12',    // 页面背景
    'bg-card': '#1e1e24',    // 卡片背景
    // ...
  }
}
```

## 详细文档

- [开发指南](./DEV.md) — 开发模式详解
- [组件文档](./docs/) — 组件 API 文档
- [设计令牌](./src/tokens/) — 设计系统
