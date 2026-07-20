#!/bin/bash
# =====================================================
# Eyes 项目开发模式配置
# =====================================================
#
# 这个脚本会在 eyes/static 下创建符号链接到 ui/src
# 这样 eyes 可以直接引用 UI 源码，无需每次构建
#
# 使用方式：
#   ./link-dev.sh      # 创建链接
#   ./link-dev.sh -u   # 取消链接
# =====================================================

set -e

EYES_STATIC="/home/zhuqin/star/infra/eyes/static"
UI_SRC="/home/zhuqin/star/infra/eyes/ui/src"
LINK_PATH="$EYES_STATIC/eyes-ui-dev"

if [ "$1" = "-u" ] || [ "$1" = "--unlink" ]; then
    echo "🔓 取消开发链接..."
    if [ -L "$LINK_PATH" ]; then
        rm "$LINK_PATH"
        echo "✓ 已删除 $LINK_PATH"
    else
        echo "链接不存在"
    fi
    exit 0
fi

echo "🔗 创建开发链接..."

# 删除旧链接（如果存在）
if [ -L "$LINK_PATH" ]; then
    rm "$LINK_PATH"
fi

# 创建符号链接
ln -s "$UI_SRC" "$LINK_PATH"

echo "✓ 已创建: $LINK_PATH → $UI_SRC"
echo ""
echo "现在可以在 eyes 项目中这样引用："
echo ""
echo "  <link rel=\"stylesheet\" href=\"/static/eyes-ui-dev/styles/base.css\">"
echo "  <link rel=\"stylesheet\" href=\"/static/eyes-ui-dev/components/button/button.css\">"
echo ""
echo "修改 ui/src/ 下的文件后，刷新 eyes 页面即可看到效果（无需重启 Docker）"
