#!/bin/bash
# =====================================================
# Eyes UI 构建脚本（发布用）
# =====================================================
#
# 使用方式：
#   ./build.sh         # 构建 dist
#   ./build.sh --copy  # 构建并复制到 eyes/static
# =====================================================

set -e

echo "🔨 构建 Eyes UI..."

# 清理旧构建
rm -rf dist

# 运行构建
npm run build

echo ""
echo "✓ 构建完成！"
echo ""
echo "产物："
echo "  dist/eyes-ui.js      # JavaScript"
echo "  dist/eyes-ui.css     # 样式"
echo "  dist/tokens.css      # 设计令牌"
echo "  dist/index.d.ts      # 类型定义"

# 如果指定了 --copy，复制到 eyes/static
if [ "$1" = "--copy" ]; then
    echo ""
    echo "📦 复制到 eyes/static/eyes-ui/dist..."
    
    TARGET="/home/zhuqin/star/infra/eyes/static/eyes-ui/dist"
    mkdir -p "$TARGET"
    
    cp dist/eyes-ui.js "$TARGET/"
    cp dist/eyes-ui.css "$TARGET/"
    
    echo "✓ 已复制到 $TARGET"
fi

echo ""
echo "下一步："
echo "  1. 测试: npm test"
echo "  2. 文档: npm run storybook"
echo "  3. 发布: npm publish"
