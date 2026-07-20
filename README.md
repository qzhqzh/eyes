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

## 项目设计文档

Eyes 正在从单机健康检查工具演进为面向 AI Agent 的多节点资源网络。项目愿景、目标架构、资源模型、通信协议、安全边界和实施路线见 [docs/README.md](docs/README.md)。

## 多节点架构预览

当前已具备节点注册、主动心跳、inventory/resources 快照和命令通道骨架。开发环境可这样验证：

```bash
# Hub：复制配置后替换全部 replace-with-* 占位值，.env 已被 Git 忽略；
# 应用会拒绝使用示例占位值启动。
cp .env.example .env

# 从旧版根目录 eyes.db 升级时自动保留备份；全新安装不会执行复制。
mkdir -p data
if [ -f eyes.db ] && [ ! -e data/eyes.db ]; then
  cp eyes.db eyes.db.pre-fleet-backup
  install -m 600 eyes.db data/eyes.db
fi

docker compose up -d --build

# Node：首次运行保存 node_id 和 Hub 凭据，后续无需 enroll-token
python3 agent/eyes-agent.py \
  --mode node \
  --hub-url http://127.0.0.1:8090 \
  --enroll-token "$EYES_HUB_ENROLL_TOKEN" \
  --state-dir ./data/agent-state \
  --once
```

登录 `http://<hub-ip>:8090/` 查看原有监控页面，登录后进入 `http://<hub-ip>:8090/fleet` 查看已连接节点和资源快照。管理密码来自 `.env` 的 `EYES_WEB_PASSWORD`。

远程节点默认只连接 HTTPS Hub；`http://127.0.0.1`、`http://localhost` 仅用于本机开发。受控测试网络若暂时没有 TLS，可显式添加 `--allow-insecure-http`。

Linux 节点可执行 `sudo sh agent/install.sh` 安装 systemd 单元和配置模板，然后编辑 `/etc/eyes/agent.env`。

基础 Compose 不挂载 Docker Socket、Nginx 和 NAS，确保新机器可直接启动。需要旧版本机扫描能力时，先检查并修改 `docker-compose.host.example.yml` 的宿主机路径，再以 Compose override 启动；Docker Socket 等同高权限入口，不应在不可信 Hub 上启用。

当前环境变量 Token 是第一阶段 bootstrap 机制，适合受控网络验证；一次性 Token、mTLS、调度器和执行器仍在后续阶段。已实现边界见 [docs/implementation-status.md](docs/implementation-status.md)。
