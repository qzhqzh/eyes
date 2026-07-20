#!/bin/bash
# Eyes UI 构建脚本
# 合并所有组件文件为单个文件

OUTPUT_JS="static/eyes-ui/dist/eyes-ui.js"
OUTPUT_CSS="static/eyes-ui/dist/eyes-ui.css"

mkdir -p static/eyes-ui/dist

echo "Building Eyes UI..."

# 合并 CSS
cat \
    static/eyes-ui/styles/variables.css \
    static/eyes-ui/styles/reset.css \
    static/eyes-ui/styles/utilities.css \
    static/eyes-ui/components/button/button.css \
    static/eyes-ui/components/card/card.css \
    static/eyes-ui/components/badge/badge.css \
    static/eyes-ui/components/input/input.css \
    static/eyes-ui/components/select/select.css \
    static/eyes-ui/components/checkbox/checkbox.css \
    static/eyes-ui/components/modal/modal.css \
    static/eyes-ui/components/toast/toast.css \
    static/eyes-ui/components/table/table.css \
    static/eyes-ui/components/pagination/pagination.css \
    static/eyes-ui/components/list/list.css \
    static/eyes-ui/components/filter-bar/filter-bar.css \
    static/eyes-ui/components/stat-card/stat-card.css \
    > "$OUTPUT_CSS"

echo "✓ Built: $OUTPUT_CSS"

# 合并 JS
cat \
    static/eyes-ui/index.js \
    static/eyes-ui/components/button/button.js \
    static/eyes-ui/components/card/card.js \
    static/eyes-ui/components/badge/badge.js \
    static/eyes-ui/components/input/input.js \
    static/eyes-ui/components/select/select.js \
    static/eyes-ui/components/checkbox/checkbox.js \
    static/eyes-ui/components/modal/modal.js \
    static/eyes-ui/components/toast/toast.js \
    static/eyes-ui/components/table/table.js \
    static/eyes-ui/components/pagination/pagination.js \
    static/eyes-ui/components/list/list.js \
    static/eyes-ui/components/filter-bar/filter-bar.js \
    static/eyes-ui/components/stat-card/stat-card.js \
    > "$OUTPUT_JS"

echo "✓ Built: $OUTPUT_JS"
echo ""
echo "Done!"
