/**
 * Eyes UI — JavaScript 组件库
 */

const EyesUI = {
    // ========== Toast 提示 ==========
    toast(message, type = 'info') {
        const toast = document.getElementById('eyes-toast');
        if (!toast) return;
        
        toast.textContent = message;
        toast.className = `e-toast e-toast-${type} visible`;
        setTimeout(() => toast.classList.remove('visible'), 3000);
    },

    // ========== FilterBar 筛选栏 ==========
    FilterBar({ items, activeKey, onFilter }) {
        return `
            <div class="e-filter-bar">
                ${items.map(item => `
                    <div class="e-filter-tag ${item.key === activeKey ? 'active' : ''}" 
                         onclick="${onFilter}('${item.key}')">
                        ${item.label}
                        ${item.count !== undefined ? `<span class="e-filter-tag-count">${item.count}</span>` : ''}
                    </div>
                `).join('')}
            </div>
        `;
    },

    // ========== List 列表 ==========
    List({ items }) {
        if (!items || items.length === 0) {
            return '<div style="text-align:center;padding:40px;color:var(--eyes-text-muted)">暂无数据</div>';
        }
        
        return `
            <div class="e-list">
                ${items.map(item => this.ListItem(item)).join('')}
            </div>
        `;
    },

    ListItem({ icon, title, desc, tag, ok = true }) {
        return `
            <div class="e-list-item">
                <div class="e-list-icon ${ok ? 'e-list-icon-success' : 'e-list-icon-danger'}">
                    ${icon || (ok ? '✓' : '✗')}
                </div>
                <div class="e-list-content">
                    <div class="e-list-title">${title}</div>
                    ${desc ? `<div class="e-list-desc">${desc}</div>` : ''}
                </div>
                ${tag ? `<span class="e-list-tag">${tag}</span>` : ''}
            </div>
        `;
    },

    // ========== Table 表格 ==========
    Table({ columns, data }) {
        if (!data || data.length === 0) {
            return '<div style="text-align:center;padding:40px;color:var(--eyes-text-muted)">暂无数据</div>';
        }
        
        return `
            <div style="overflow-x:auto">
                <table class="e-table">
                    <thead>
                        <tr>
                            ${columns.map(col => `
                                <th style="${col.width ? `width:${col.width}` : ''}">${col.title}</th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(row => `
                            <tr>
                                ${columns.map(col => `
                                    <td>${col.render ? col.render(row[col.key], row) : (row[col.key] || '')}</td>
                                `).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    },

    // ========== Pagination 分页 ==========
    Pagination({ current, total, pageSize, onPageChange }) {
        const totalPages = Math.ceil(total / pageSize);
        if (totalPages <= 1) {
            return `<div class="e-pagination"><span class="e-pagination-info">共 ${total} 条</span></div>`;
        }
        
        let html = '<div class="e-pagination">';
        
        // 上一页
        html += `<button class="e-pagination-item" ${current === 1 ? 'disabled' : ''} onclick="${onPageChange}(${current - 1})">‹</button>`;
        
        // 页码
        const maxVisible = 5;
        let startPage = Math.max(1, current - Math.floor(maxVisible / 2));
        let endPage = Math.min(totalPages, startPage + maxVisible - 1);
        
        if (endPage - startPage < maxVisible - 1) {
            startPage = Math.max(1, endPage - maxVisible + 1);
        }
        
        if (startPage > 1) {
            html += `<button class="e-pagination-item" onclick="${onPageChange}(1)">1</button>`;
            if (startPage > 2) html += '<span class="e-pagination-ellipsis">...</span>';
        }
        
        for (let i = startPage; i <= endPage; i++) {
            html += `<button class="e-pagination-item ${i === current ? 'active' : ''}" onclick="${onPageChange}(${i})">${i}</button>`;
        }
        
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) html += '<span class="e-pagination-ellipsis">...</span>';
            html += `<button class="e-pagination-item" onclick="${onPageChange}(${totalPages})">${totalPages}</button>`;
        }
        
        // 下一页
        html += `<button class="e-pagination-item" ${current === totalPages ? 'disabled' : ''} onclick="${onPageChange}(${current + 1})">›</button>`;
        
        html += `<span class="e-pagination-info">共 ${total} 条</span>`;
        html += '</div>';
        
        return html;
    },

    // ========== Modal 弹窗 ==========
    Modal({ id, title, body, footer }) {
        return `
            <div class="e-modal-mask" onclick="EyesUI.closeModal('${id}')"></div>
            <div class="e-modal" id="${id}">
                <div class="e-modal-content">
                    ${title ? `
                        <div class="e-modal-header">
                            <div class="e-modal-title">${title}</div>
                            <button class="e-modal-close" onclick="EyesUI.closeModal('${id}')">✕</button>
                        </div>
                    ` : ''}
                    <div class="e-modal-body">${body}</div>
                    ${footer ? `<div class="e-modal-footer">${footer}</div>` : ''}
                </div>
            </div>
        `;
    },

    showModal(id) {
        const modal = document.getElementById(id);
        const mask = modal.previousElementSibling;
        if (modal) modal.classList.add('visible');
        if (mask) mask.classList.add('visible');
    },

    closeModal(id) {
        const modal = document.getElementById(id);
        const mask = modal.previousElementSibling;
        if (modal) modal.classList.remove('visible');
        if (mask) mask.classList.remove('visible');
    },

    // ========== Switch 开关 ==========
    Switch({ id, checked }) {
        return `<div class="e-switch ${checked ? 'active' : ''}" id="${id}" onclick="this.classList.toggle('active')"></div>`;
    },

    // ========== Checkbox 复选框 ==========
    Checkbox({ id, label, checked }) {
        return `
            <label class="e-checkbox">
                <input type="checkbox" class="e-checkbox-input" id="${id}" ${checked ? 'checked' : ''}>
                <span class="e-checkbox-label">${label}</span>
            </label>
        `;
    },

    // ========== Badge 徽章 ==========
    Badge({ text, variant = 'primary' }) {
        return `<span class="e-badge e-badge-${variant}">${text}</span>`;
    },

    // ========== Button 按钮 ==========
    Button({ text, variant = 'primary', size, onclick, disabled, loading }) {
        const classes = [
            'e-btn',
            `e-btn-${variant}`,
            size ? `e-btn-${size}` : '',
            loading ? 'e-btn-loading' : ''
        ].filter(Boolean).join(' ');
        
        return `
            <button class="${classes}" ${onclick ? `onclick="${onclick}"` : ''} ${disabled ? 'disabled' : ''}>
                ${text}
            </button>
        `;
    },

    // ========== Card 卡片 ==========
    Card({ title, actions, body, footer }) {
        return `
            <div class="e-card">
                ${title ? `
                    <div class="e-card-header">
                        <div class="e-card-title">${title}</div>
                        ${actions ? `<div class="e-card-actions">${actions}</div>` : ''}
                    </div>
                ` : ''}
                <div class="e-card-body">${body}</div>
                ${footer ? `<div class="e-card-footer">${footer}</div>` : ''}
            </div>
        `;
    },

    // ========== StatCard 统计卡片 ==========
    StatCard({ label, value, variant }) {
        return `
            <div class="e-stat-card">
                <div class="e-stat-label">${label}</div>
                <div class="e-stat-value ${variant ? `e-stat-value-${variant}` : ''}">${value}</div>
            </div>
        `;
    },

    // ========== Input 输入框 ==========
    Input({ id, type = 'text', value, placeholder, size }) {
        const classes = ['e-input', size ? `e-input-${size}` : ''].filter(Boolean).join(' ');
        return `<input type="${type}" class="${classes}" id="${id}" value="${value || ''}" placeholder="${placeholder || ''}">`;
    },

    // ========== Select 选择器 ==========
    Select({ id, options, value }) {
        return `
            <select class="e-select" id="${id}">
                ${options.map(opt => `
                    <option value="${opt.value}" ${opt.value === value ? 'selected' : ''}>${opt.label}</option>
                `).join('')}\n            </select>
        `;
    },

    // ========== RingChart 环形图 ==========
    RingChart({ value, total, size = 120, strokeWidth = 8, color, label }) {
        const radius = (size - strokeWidth) / 2;
        const circumference = 2 * Math.PI * radius;
        const percent = total > 0 ? (value / total) * 100 : 0;
        const offset = circumference - (percent / 100) * circumference;
        
        // 根据百分比确定颜色
        if (!color) {
            if (percent >= 90) color = 'var(--eyes-success)';
            else if (percent >= 70) color = 'var(--eyes-warning)';
            else color = 'var(--eyes-danger)';
        }
        
        return `
            <div class="e-ring-chart" style="width: ${size}px; height: ${size}px;">
                <svg width="${size}" height="${size}">
                    <circle class="e-ring-chart-track"
                            cx="${size / 2}" cy="${size / 2}" r="${radius}"
                            stroke-width="${strokeWidth}" />
                    <circle class="e-ring-chart-fill"
                            cx="${size / 2}" cy="${size / 2}" r="${radius}"
                            stroke-width="${strokeWidth}"
                            stroke="${color}"
                            stroke-dasharray="${circumference}"
                            stroke-dashoffset="${offset}"
                            stroke-linecap="round" />
                </svg>
                <div class="e-ring-chart-center">
                    <div class="e-ring-chart-value">${Math.round(percent)}%</div>
                    ${label ? `<div class="e-ring-chart-label">${label}</div>` : ''}
                </div>
            </div>
        `;
    }
};

// 导出到全局
window.EyesUI = EyesUI;
