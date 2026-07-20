# 实现状态

本文区分当前代码与目标设计。更新时间：2026-07-20。

## 已实现

### Hub 控制面基础

- `fleet.py` 初始化独立于旧单机检查表的多节点控制面表：
  - `nodes`
  - `node_credentials`
  - `node_snapshots`
  - `node_commands`
  - `workloads`
  - `resource_claims`
  - `leases`
  - `audit_events`
- 启动时创建 `hub-local` 兼容节点，为旧本机数据迁移预留身份。
- Flask 注册 `/api/v1` Blueprint。
- Web 登录用户可以查看节点、节点快照和 pending Workload。

### Hub-Agent 协议纵切

- `POST /api/v1/enroll`
- `POST /api/v1/node/heartbeat`
- `PUT /api/v1/node/inventory`
- `PUT /api/v1/node/resources`
- `GET /api/v1/node/commands`
- `POST /api/v1/node/commands/<id>/ack`
- 节点 Bearer Token 只保存 SHA-256 摘要，API 同时绑定 `X-Eyes-Node-ID`。
- 心跳使用 boot ID 和单调 sequence，拒绝同一次启动中的倒退序列。
- 快照使用 generation 和内容摘要，支持幂等重试并拒绝旧版本覆盖。

### Node Agent

- 持久 UUID `node_id` 和 Hub credential，使用原子写和 `0600` 权限。
- 主动出站注册、心跳、inventory/resources 上报和命令查询。
- 网络失败采用有界指数退避。
- 发现操作系统、地址、systemd、CPU、内存、根文件系统和基础 capability。
- `node` 与 `legacy-server` 两种模式共存，旧部署没有被直接删除。
- systemd 单元改为无入站 Node 模式、DynamicUser、StateDirectory 和基础沙箱设置。
- `agent/install.sh` 将 Agent、客户端、systemd 单元和配置模板安装到单元声明的固定路径。
- `/fleet` 提供最小节点列表与 Node Detail 页面，可查看 Inventory 和 Resources 快照。

### 验证

- Fleet 存储、协议鉴权、快照幂等、序列保护和 Workload 骨架单元测试。
- NodeStateStore、HubClient 和退避测试。
- 真实 Agent 子进程到临时 Flask Hub 的注册、心跳、双快照和命令拉取测试。
- Flask 完整应用加载和 `/api/v1` 路由烟测。

## 仅有骨架，尚未完成

- Workload 可以进入 `pending`，但还没有调度器、ResourceClaim 分配或 Lease controller。
- 命令表和拉取/确认 API 已存在，但 Agent 不执行任何 Hub 命令。
- Hub 的 `wait` 参数尚未实现真正长轮询。
- `hub-local` 还没有把旧 `check_items` 和 `resource_metrics` 完整迁移到 node_id 模型。
- 节点状态尚未根据心跳窗口自动从 `ready` 转为 `stale`。
- Fleet 已有最小页面，但尚未提供资源聚合视图和 Topology 页面。

## 安全限制

- `EYES_HUB_ENROLL_TOKEN` 当前是共享 bootstrap Token，不是一次性 Token。
- 同一 `node_id` 已注册后拒绝用 bootstrap Token 覆盖凭据，避免直接劫持已注册节点。
- Agent 在发起注册前持久生成节点凭据，同一凭据可幂等重放，避免响应丢失导致永久冲突。
- 节点凭据当前是 Bearer Token，尚未升级为短期证书和 mTLS。
- Agent 默认拒绝向非本机明文 HTTP Hub 发送注册或节点凭据；远程生产连接要求 HTTPS。
- Compose 将数据库持久化到 `data/eyes.db`；旧版根目录数据库升级前必须按 README 备份并迁移。
- Agent 自报 roles/labels 尚未经过管理员审批，调度器落地前必须区分声明值与批准值。
- Workload executor、MaintenanceAction 和 ShellSession 均未启用，因此当前没有新增远程执行入口。

## 下一批建议

1. 一次性 enrollment token、撤销/轮换和节点批准流程。
2. `ready/stale/offline` 状态控制器与 Fleet 资源聚合视图。
3. 将旧本机检查和资源数据归属到 `hub-local`。
4. 实现只读资源匹配解释，再实现 Reservation/Lease，不直接跳到命令执行。
