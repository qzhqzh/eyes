# Eyes Dashboard — Design System

## 1. 配色方案

### 主色调
| 用途 | 颜色 | HEX | 应用场景 |
|------|------|-----|----------|
| 主色（品牌色） | 深紫蓝 | `#6366f1` | 按钮、链接、选中态、进度条 |
| 主色-悬停 | 紫蓝 | `#4f46e5` | 按钮 hover 态 |
| 强调色-正向 | 翠绿 | `#10b981` | 正常状态、成功提示、通过 |
| 强调色-警示 | 琥珀橙 | `#f59e0b` | 警告状态、需注意 |
| 强调色-危险 | 玫瑰红 | `#ef4444` | 异常状态、失败、错误 |

### 背景色层级
| 层级 | 用途 | HEX |
|------|------|-----|
| L0 — 页面底色 | 全局最深背景 | `#0f0f12` |
| L1 — 侧边栏 | 导航区域 | `#1a1a1f` |
| L2 — 卡片 | 内容容器 | `#1e1e24` |
| L3 — 卡片悬停 | 交互反馈 | `#26262e` |
| L4 — 输入框/选区 | 表单元素 | `#2a2a33` |

### 文字颜色层级
| 层级 | 用途 | HEX |
|------|------|-----|
| 主标题 | 页面标题、选中项 | `#f8fafc` |
| 正文 | 内容文字、数值 | `#cbd5e1` |
| 次要文字 | 日期、描述、标签 | `#64748b` |
| 禁用文字 | 不可交互元素 | `#475569` |

### 边框与分割线
| 用途 | HEX |
|------|-----|
| 默认边框 | `#2d2d35` |
| 悬停边框 | `#3d3d47` |
| 分割线 | `#1f1f27` |

---

## 2. 字体层级（精确复刻参考图）

### 字体家族
```css
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 
             'Inter', 'Noto Sans SC', sans-serif;
```

### 字号层级
| 层级 | 字号 | 字重 | 行高 | 颜色 | 应用场景 |
|------|------|------|------|------|----------|
| H1 | 24px | 500 (Medium) | 1.3 | `#f8fafc` | 页面主标题（Welcome back） |
| H2 | 16px | 500 (Medium) | 1.4 | `#f8fafc` | 模块标题（Budget, Spending） |
| H3 | 14px | 500 (Medium) | 1.4 | `#f8fafc` | 卡片内子标题 |
| 数值-大 | 28px | 700 (Bold) | 1.2 | `#f8fafc` | 关键数值（$4,570,790） |
| 数值-中 | 16px | 600 (SemiBold) | 1.3 | `#f8fafc` | 次要数值 |
| Body | 14px | 400 (Regular) | 1.5 | `#cbd5e1` | 正文内容 |
| Small | 13px | 400 (Regular) | 1.4 | `#64748b` | 描述文字 |
| Caption | 12px | 400 (Regular) | 1.4 | `#64748b` | 标签、时间戳、辅助信息 |

### 语义颜色
- 正向数值/增长：`#10b981` (绿色)
- 负向数值/减少：`#ef4444` (红色)
- 警示数值：`#f59e0b` (橙色)

---

## 3. 间距与留白（精确复刻参考图）

### 全局间距
- 页面外边距：`24px`
- 侧边栏宽度：`220px`
- 侧边栏与内容区间距：`24px`
- 侧边栏内边距：`16px 12px`

### 卡片间距
- 卡片之间的间距：`16px`
- 卡片内边距：`20px`
- 卡片内元素间距：`16px`

### 组件内部间距
- 按钮内边距：`8px 16px` (小) / `10px 20px` (中)
- 表单输入框内边距：`10px 14px`
- 列表项间距：`12px`
- 标题与内容间距：`12px`
- 徽章内边距：`4px 10px`

### 响应式断点
| 断点 | 宽度 | 布局变化 |
|------|------|----------|
| Mobile | < 768px | 单列，侧边栏折叠 |
| Tablet | 768px - 1024px | 双列压缩 |
| Desktop | > 1024px | 完整布局 |

---

## 4. 组件样式（精确复刻参考图）

### 圆角规范
| 组件 | 圆角半径 | 说明 |
|------|----------|------|
| 卡片 | `16px` | 大圆角，柔和现代感 |
| 按钮 | `8px` | 中等圆角 |
| 输入框 | `8px` | 与按钮一致 |
| 进度条 | `4px` (高度8px的一半) | 胶囊形 |
| 徽章/标签 | `6px` | 小圆角 |
| 弹窗 | `20px` | 大圆角，突出层级 |
| 头像/图标容器 | `10px` | 中等圆角 |

### 卡片
```css
.card {
  background: #1e1e24;
  border-radius: 16px;
  border: 1px solid #2d2d35;
  padding: 20px;
  transition: border-color 0.2s ease;
}
.card:hover {
  border-color: #3d3d47;
}
```

### 按钮
```css
/* 主按钮 */
.btn-primary {
  background: #6366f1;
  color: #ffffff;
  border: none;
  border-radius: 8px;
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.2s ease;
}
.btn-primary:hover {
  background: #4f46e5;
}

/* 次要按钮 */
.btn-secondary {
  background: transparent;
  color: #cbd5e1;
  border: 1px solid #2d2d35;
  border-radius: 8px;
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
}
.btn-secondary:hover {
  background: #26262e;
  border-color: #3d3d47;
}

/* 小按钮 */
.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
  border-radius: 6px;
}

/* 危险按钮 */
.btn-danger {
  background: #ef4444;
  color: #ffffff;
}
.btn-danger:hover {
  background: #dc2626;
}

/* 成功按钮 */
.btn-success {
  background: #10b981;
  color: #ffffff;
}
.btn-success:hover {
  background: #059669;
}
```

### 状态指示器
```css
/* 正常状态 */
.status-ok {
  color: #10b981;
  background: rgba(16, 185, 129, 0.1);
}

/* 警告状态 */
.status-warning {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}

/* 异常状态 */
.status-error {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}
```

### 进度条
```css
.progress-bar {
  height: 8px;
  background: #2a2a33;
  border-radius: 4px;
  overflow: hidden;
}
.progress-fill {
  border-radius: 4px;
  transition: width 0.3s ease;
}
.progress-fill.ok { background: #10b981; }
.progress-fill.warning { background: #f59e0b; }
.progress-fill.error { background: #ef4444; }
```

### 导航栏
```css
.sidebar {
  background: #1a1a1f;
  width: 220px;
  padding: 16px 12px;
}

.nav-item {
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 400;
  color: #64748b;
  transition: all 0.2s ease;
}
.nav-item:hover {
  background: #26262e;
  color: #cbd5e1;
}
.nav-item.active {
  background: #26262e;
  color: #f8fafc;
  font-weight: 500;
}
```

### 输入框
```css
.input {
  background: #2a2a33;
  border: 1px solid #2d2d35;
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 14px;
  color: #f8fafc;
  transition: border-color 0.2s ease;
}
.input:focus {
  border-color: #6366f1;
  outline: none;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}
```

### 弹窗/对话框
```css
.modal {
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(4px);
}
.modal-content {
  background: #1e1e24;
  border: 1px solid #2d2d35;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}
```

### 徽章/标签
```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}
.badge-success {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}
.badge-danger {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}
.badge-primary {
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
}
```

### Toast 提示
```css
.toast {
  border-radius: 8px;
  padding: 12px 20px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
}
.toast-success { background: #10b981; color: #fff; }
.toast-error { background: #ef4444; color: #fff; }
.toast-info { background: #6366f1; color: #fff; }
```

### 列表/表格
```css
/* 列表容器 */
.list {
  display: flex;
  flex-direction: column;
}

/* 列表项 */
.list-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-bottom: 1px solid #1f1f27;
  transition: background 0.2s ease;
}
.list-item:last-child {
  border-bottom: none;
}
.list-item:hover {
  background: #26262e;
}

/* 列表项 - 状态图标 */
.list-item-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  flex-shrink: 0;
}
.list-item-icon.ok {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}
.list-item-icon.error {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

/* 列表项 - 内容区 */
.list-item-content {
  flex: 1;
  min-width: 0;
}
.list-item-name {
  font-size: 14px;
  font-weight: 500;
  color: #f8fafc;
  margin-bottom: 2px;
}
.list-item-detail {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 列表项 - 右侧操作/状态 */
.list-item-meta {
  font-size: 12px;
  color: #64748b;
  flex-shrink: 0;
}

/* 列表项 - 分类标签 */
.list-item-tag {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  background: #2a2a33;
  color: #cbd5e1;
}
```

### 筛选标签栏
```css
.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.filter-tag {
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  background: #2a2a33;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}
.filter-tag:hover {
  background: #333340;
  color: #cbd5e1;
}
.filter-tag.active {
  background: #6366f1;
  color: #ffffff;
}
.filter-tag .count {
  margin-left: 6px;
  opacity: 0.7;
}
```

---

## 5. 整体布局

### 页面结构
```
┌─────────────────────────────────────────────────────────┐
│  ┌──────────┐  ┌──────────────────────────────────────┐ │
│  │          │  │  Header (标题 + 操作按钮)            │ │
│  │          │  ├──────────────────────────────────────┤ │
│  │  Side    │  │  Summary Cards (统计概览)            │ │
│  │  bar     │  ├──────────────────┬───────────────────┤ │
│  │          │  │                  │                   │ │
│  │  (导航)  │  │  Main Content    │  Side Panel       │ │
│  │          │  │  (主内容)        │  (辅助信息)       │ │
│  │          │  │                  │                   │ │
│  │          │  │                  │                   │ │
│  └──────────┘  └──────────────────┴───────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### 栅格系统
- 主内容区使用 CSS Grid 或 Flexbox
- 左右分栏比例：`6:4` 或 `7:5`
- 统计卡片：`4` 列等宽
- 响应式：窄屏自动堆叠

### 侧边栏结构
```
┌──────────────┐
│  Logo        │
│  ─────────── │
│  Dashboard   │  ← 选中态
│  监控项      │
│  设置        │
│  ─────────── │
│  版本信息    │
│  退出        │
└──────────────┘
```

---

## 6. 图标风格

- 使用 Lucide Icons 或 Heroicons
- 线条风格，2px 线宽
- 尺寸：16px (小) / 20px (中) / 24px (大)
- 颜色跟随文字颜色

---

## 7. 动效规范

- 过渡时间：`0.2s` (快速) / `0.3s` (标准)
- 缓动函数：`ease` 或 `cubic-bezier(0.4, 0, 0.2, 1)`
- 悬停效果：背景色、边框色变化
- 进入动画：淡入 + 轻微上移

---

## 8. 实际应用示例

### 状态仪表盘布局
```
┌─────────────────────────────────────────────────────────┐
│  👁 Eyes — 服务健康监控                    [设置] [退出] │
├─────────────────────────────────────────────────────────┤
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐      │
│  │   24    │ │   22    │ │    2    │ │  12:30  │      │
│  │ 监控项  │ │  正常   │ │  异常   │ │ 上次检查│      │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘      │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐ ┌─────────────────────────┐│
│  │ Docker 容器             │ │ Systemd 服务            ││
│  │ ✓ nginx    running (2d) │ │ ✓ docker   active      ││
│  │ ✓ redis    running (5h) │ │ ✓ ssh      active      ││
│  │ ✗ mysql    stopped      │ │                         ││
│  └─────────────────────────┘ └─────────────────────────┘│
│  ┌─────────────────────────┐ ┌─────────────────────────┐│
│  │ HTTP 端点               │ │ 端口扫描                ││
│  │ ✓ example.com 200 (45ms)│ │ ✓ :22   tcp (sshd)     ││
│  │ ✓ api.test    200 (12ms)│ │ ✓ :80   tcp (nginx)    ││
│  └─────────────────────────┘ └─────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

---

*Design System v1.0 — Eyes Dashboard*
*参考风格：深色主题、现代仪表盘、数据可视化*
