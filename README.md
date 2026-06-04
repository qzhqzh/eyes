# eyes — 服务健康检查工具

一行命令检查本机所有服务是否正常运行。支持邮件告警和每日报告。

**特性：**
- 支持 Docker 容器、Systemd 服务、HTTP 端点、端口监听、自定义命令
- **Nginx 自动发现**：从 nginx 配置自动识别子域名服务，无需手动维护
- 邮件告警（SMTP）和每日报告
- 终端彩色输出、JSON 输出、实时刷新

## 快速开始

```bash
# 1. 安装依赖
pip install pyyaml

# 2. 复制配置文件
cp config.example.yaml config.yaml

# 3. 编辑配置，填入你的邮箱和 SMTP 信息
vim config.yaml

# 4. 运行检查
python3 check.py
```

## 目录结构

```
eyes/
├── check.py                主脚本
├── config.example.yaml     配置模板（可提交到公开仓库）
├── config.yaml             实际配置（含密码，已 gitignore）
├── .gitignore              Git 忽略规则
└── conf.d/                 服务列表（按分类存放）
    ├── docker.yaml         Docker 容器（手动管理）
    ├── http.yaml           HTTP 端点（手动管理）
    ├── systemd.yaml        Systemd 服务
    ├── port.yaml           端口监听
    ├── command.yaml        自定义命令
    ├── _nginx_docker.yaml  Nginx 自动发现（由 --sync 生成）
    └── _nginx_http.yaml    Nginx 自动发现（由 --sync 生成）
```

## 用法

```bash
python3 check.py              # 终端检查
python3 check.py --json       # JSON 输出
python3 check.py --watch 10   # 每 10 秒刷新
python3 check.py --quiet      # 只显示失败项
python3 check.py --alert      # 有失败才发邮件
python3 check.py --report     # 始终发邮件报告

# Nginx 自动发现（推荐）
python3 check.py --sync             # 同步 nginx 路由 + 终端检查
python3 check.py --sync --alert     # 同步 + 异常发邮件
python3 check.py --sync --report    # 同步 + 每日报告
```

## Nginx 自动发现

如果你使用 nginx 反向代理，`--sync` 会自动：

1. 扫描 `nginx/conf.d/*.conf` 文件
2. 解析 `server_name` → `proxy_pass` 端口映射
3. 找到每个端口对应的 Docker 容器
4. 自动生成 `_nginx_docker.yaml` 和 `_nginx_http.yaml`
5. 移除已下线服务的监控条目

**使用方式：**

```bash
# 设置 nginx 配置目录（默认 /etc/nginx/conf.d）
python3 check.py --sync --nginx-conf-dir /path/to/nginx/conf.d
```

**工作流：**
- 新增服务：添加 nginx conf → 下次 `--sync` 自动发现
- 移除服务：删除 nginx conf → 下次 `--sync` 自动排除
- 手动服务：在 `docker.yaml` / `http.yaml` 中维护

## 增删服务

### 手动添加

直接编辑 `conf.d/` 下对应文件：

```bash
# 加一个 Docker 容器
echo '- { name: "新服务", target: my-container-1 }' >> conf.d/docker.yaml

# 删一个：注释掉或删掉那一行
# - { name: "旧服务", target: old-container }

# 加一个新分类：新建 conf.d/xxx.yaml
```

### 自动发现（推荐）

使用 nginx 反向代理的服务无需手动添加：

```bash
# 1. 添加 nginx 配置
cat > /etc/nginx/conf.d/my-service.conf << 'EOF'
server {
    listen 80;
    server_name my-service.example.com;
    location / {
        proxy_pass http://127.0.0.1:8080;
    }
}
EOF

# 2. 重新加载 nginx
nginx -s reload

# 3. 运行同步（自动发现新服务）
python3 check.py --sync
```

## 定时任务

```bash
# 每小时整点检查（自动同步 nginx + 异常发邮件）
0 * * * * cd /path/to/eyes && python3 check.py --sync --alert >> /var/log/eyes.log 2>&1

# 每天 9:00 发完整报告
0 9 * * * cd /path/to/eyes && python3 check.py --sync --report >> /var/log/eyes.log 2>&1
```

## 退出码

- `0` — 全部通过
- `1` — 有失败项

## 环境变量（可选）

可以通过环境变量覆盖配置：

```bash
export EYES_EMAIL_FROM="alert@example.com"
export EYES_EMAIL_TO="admin@example.com"
export EYES_SMTP_HOST="smtp.example.com"
export EYES_SMTP_PASSWORD="your_password"

python3 check.py
```

## License

MIT
