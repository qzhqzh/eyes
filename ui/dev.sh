#!/bin/bash
# =====================================================
# Eyes UI 开发模式启动脚本
# =====================================================
#
# 使用方式：
#   ./dev.sh          # 启动 UI 开发服务器
#   ./dev.sh link     # 创建符号链接到 eyes
#   ./dev.sh unlink   # 取消符号链接
#   ./dev.sh build    # 构建并复制到 eyes
#
# 开发流程：
#   1. 运行 ./dev.sh 启动开发服务器
#   2. 在浏览器打开 http://localhost:5173 预览组件
#   3. 修改 src/ 下的文件，浏览器自动刷新
#   4. 稳定后运行 ./dev.sh build 构建并部署
# =====================================================

set -e

UI_DIR="$(cd "$(dirname "$0")" && pwd)"
EYES_DIR="$(dirname "$UI_DIR")"

# 颜色
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# 检查依赖
check_deps() {
    if [ ! -d "$UI_DIR/node_modules" ]; then
        print_info "安装依赖..."
        cd "$UI_DIR" && npm install
        echo ""
    fi
}

# 启动开发服务器
start_dev() {
    echo ""
    echo "🚀 Eyes UI 开发服务器"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    print_info "组件预览：http://localhost:5173"
    print_info "修改 src/ 下的文件，浏览器自动刷新"
    echo ""
    print_warning "按 Ctrl+C 停止服务器"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    cd "$UI_DIR" && npx vite --config vite.config.dev.ts
}

# 创建符号链接
create_link() {
    local TARGET="$EYES_DIR/static/eyes-ui-dev"
    
    print_info "创建符号链接..."
    
    # 删除旧链接
    if [ -L "$TARGET" ]; then
        rm "$TARGET"
    fi
    
    # 创建链接
    ln -s "$UI_DIR/src" "$TARGET"
    
    print_success "已创建: $TARGET → $UI_DIR/src"
    echo ""
    echo "现在可以在 eyes 模板中引用："
    echo ""
    echo '  <link rel="stylesheet" href="/static/eyes-ui-dev/styles/base.css">'
    echo '  <link rel="stylesheet" href="/static/eyes-ui-dev/components/button/button.css">'
    echo ""
}

# 取消符号链接
remove_link() {
    local TARGET="$EYES_DIR/static/eyes-ui-dev"
    
    if [ -L "$TARGET" ]; then
        rm "$TARGET"
        print_success "已删除符号链接"
    else
        print_warning "符号链接不存在"
    fi
}

# 构建并复制
build_and_copy() {
    print_info "构建 Eyes UI..."
    cd "$UI_DIR" && npm run build
    
    print_info "复制到 eyes/static..."
    local TARGET="$EYES_DIR/static/eyes-ui/dist"
    mkdir -p "$TARGET"
    cp -r dist/* "$TARGET/"
    
    print_success "构建完成并复制到 $TARGET"
    echo ""
    print_info "重启 eyes Docker:"
    echo "  cd $EYES_DIR && docker compose up -d"
}

# 显示帮助
show_help() {
    echo ""
    echo "Eyes UI 开发工具"
    echo ""
    echo "用法："
    echo "  ./dev.sh          启动开发服务器"
    echo "  ./dev.sh link     创建符号链接到 eyes"
    echo "  ./dev.sh unlink   取消符号链接"
    echo "  ./dev.sh build    构建并复制到 eyes"
    echo "  ./dev.sh help     显示帮助"
    echo ""
}

# 主逻辑
case "${1:-dev}" in
    dev|start)
        check_deps
        start_dev
        ;;
    link)
        create_link
        ;;
    unlink)
        remove_link
        ;;
    build)
        check_deps
        build_and_copy
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_warning "未知命令: $1"
        show_help
        exit 1
        ;;
esac
