# 演进路线

## 当前基线

当前仓库是 Flask + SQLite + APScheduler Hub，以及一个由 Hub 主动访问的宿主机 HTTP Agent。数据库和检查链路默认只有一台机器，资源采集与当前宿主机路径、Docker Socket、Nginx 和 WireGuard 接口存在耦合。

路线图遵循“先形成可靠状态闭环，再开放执行”的顺序。

## Phase 0：架构护栏与节点化数据模型

目标：现有单机功能不退化，为多节点准备稳定边界。

- 引入 `node_id`，为现有数据迁移出默认 Hub 节点。
- 将 Hub 本机资源采集改为相同的 Agent 快照语义。
- 将 APScheduler 从 Web worker 中拆出为唯一 worker。
- Secret、默认密码和 Agent 认证完成最低安全整改。
- 定义 `nodes`、`capabilities`、`resource_slices` 和版本字段。

验收：现有页面仍可使用；所有检查和资源数据都能明确追溯到节点。

## Phase 1：主动连接的多节点 Agent

目标：一条命令接入 NAT 后的 Linux 节点。

- Agent 持久 `node_id`、注册 Token 和节点凭据。
- HTTPS 心跳、inventory/resource 快照、事件批量上报。
- 长轮询命令通道和本地有界 WAL。
- Hub 节点列表、状态机和版本分布。
- systemd 安装包和不含机器绝对路径的 service unit。

验收：

- 新机器安装后 30 秒内出现在 Hub。
- Hub 不需要访问节点任何端口。
- 三个心跳窗口后节点进入 `stale`，历史资产不丢失。
- Hub 中断并恢复后，Agent 自动重连并完成状态对账。

## Phase 2：能力与全局资源目录

目标：Consumer Agent 能准确回答“哪里可以做这件事”。

- 插件式 Collector。
- role/location/labels 与探测事实分离。
- capacity、allocatable、observed_used、health。
- Docker、systemd、网络、GPU、模型/数据缓存索引。
- Fleet、Node Detail、Resources 和 Topology 页面。
- `GET /resources` 与 `POST /placements:explain`。

验收：同一查询能按能力、资源、位置、信任域和健康状态筛选节点，并解释不满足原因。

## Phase 2.5：节点维护与修复通道

该阶段可与 Phase 3 并行，目标是让有权限的人或自动化 Agent 安全进入节点诊断和修复环境。

- 先实现结构化 MaintenanceAction 和命令 allowlist。
- 增加 `eyes.io/maintenance.shell` capability 与独立 RBAC。
- 优先接入短期 SSH Certificate + overlay 直连。
- 再实现 Agent 主动连接承载的 PTY，解决节点不可直达场景。
- 加入会话 TTL、空闲超时、审批、sudo 分级和审计/录制策略。

验收：普通 `workload.submit` 身份无法打开 shell；被授权身份只能进入允许节点和权限级别；会话到期后凭据不可再次使用；所有会话均可追溯 actor、reason 和时间线。

## Phase 3：单节点资源调度闭环

目标：AI Agent 可安全提交第一个真实任务。

- Workload、ResourceClaim、Reservation、Lease 和执行状态机。
- Filter/Score/Reserve/Permit/Bind 调度器。
- 节点 Prepare、Lease fencing 和续租。
- 受限容器执行器、cgroup 限制、日志和小型结果回传。
- REST 北向 API 和 MCP Server 薄适配层。

验收：

- 两个并发请求不能重复占用同一独占 GPU。
- 节点拒绝资源不足或过期 Lease。
- Hub/Agent 任一重启后，不重复启动已执行命令。
- Consumer Agent 能提交、查询、取消任务并获得结果。

## Phase 4：数据面与利用率优化

目标：不仅能运行，还能减少搬运、等待和资源碎片。

- Artifact 存储与校验和。
- 数据和模型缓存局部性评分。
- batch pack、service spread、GPU 碎片评分。
- 按节点设置系统保留、可调度窗口和功耗/成本权重。
- OpenTelemetry 指标出口和独立时序存储。

验收：调度事件能解释选择节点的主要评分项；重复模型任务优先命中已有缓存节点。

## Phase 5：队列、公平性和多运行时适配

按真实需求选择性实现：

- 用户/项目配额和公平共享。
- 可抢占批处理任务。
- Ray、Nomad 或 Kubernetes 执行适配器。
- 多节点原子资源声明和 gang scheduling。
- PostgreSQL、横向扩展 Gateway、NATS JetStream。

## 每阶段工程约束

- 先定义协议测试和状态机不变量，再实现 UI。
- 所有跨节点写操作必须幂等。
- 不以高频指标数据库代替资源 Lease 账本。
- 不在稳定单节点执行前实现多节点调度。
- 不在出现真实吞吐瓶颈前引入消息总线。
- UI 展示必须能追溯资源数据来源、generation 和更新时间。

## 建议的首个开发切片

第一个切片只做：

1. `nodes` 表和默认 Hub 节点迁移。
2. Agent 生成持久 `node_id`。
3. `POST /api/v1/node/heartbeat`。
4. Hub 节点列表 API 和最小页面。
5. Agent systemd 安装脚本。

它能尽早验证节点身份、主动出站和离线状态三个最大架构假设，且不会提前引入执行风险。
