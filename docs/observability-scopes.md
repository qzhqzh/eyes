# 观测作用域与统计口径

Eyes 当前同时保留两类观测，界面和 API 不应混用它们的统计口径。

## Hub 本机健康

- 页面：`/`
- 数据：旧版 `check_items`、`check_results`、`resource_metrics`
- 作用域：当前 Hub 配置的 Docker、Systemd、Cron、HTTP、端口和命令检查
- 执行：Web 端可手动“扫描服务”；设置 `EYES_ENABLE_SCHEDULED_CHECKS=1` 后，已配置检查项由 Hub 后台按 `check_interval` 周期执行

这些检查尚未带 `node_id`，因此不能解释为整个 Fleet 的服务健康度。部署在容器中时，Docker Socket、宿主机 Agent、网络模式和挂载路径会决定 Hub 能观察到哪些宿主机资源。

如果宿主机已经通过 `cron_check.py` 或 `check.py --alert` 定时运行检查，应保持 `EYES_ENABLE_SCHEDULED_CHECKS=0`，避免重复检查和重复告警。

## Fleet 联通与资源

- 页面：`/fleet`
- API：`GET /api/v1/nodes`、`GET /api/v1/fleet/summary`
- 数据：各 Node Agent 主动上报的 heartbeat、Inventory 和 Resources 最新快照
- 作用域：全部已注册节点；资源容量只汇总当前 `online` 且有 Resources 快照的节点

联通状态由 Hub 根据最后心跳动态计算，不修改节点生命周期字段：

- `online`：最后心跳不超过 90 秒
- `stale`：超过 90 秒但不超过 300 秒
- `offline`：超过 300 秒
- `unknown`：尚未收到有效心跳

阈值可通过 `EYES_NODE_ONLINE_SECONDS` 和 `EYES_NODE_OFFLINE_SECONDS` 调整。离线节点的资产和最后快照会保留，但不会计入当前在线资源容量。

## Hub 节点的过渡实现

Hub 启动时会让 `hub-local` 每 30 秒发布本地心跳和运行环境快照，因此控制面自身可以在 Fleet 中正确显示在线。该快照标记为 `eyes.io/source=hub-runtime`，表示容器或进程看到的运行环境。

如果要把 Hub 物理宿主机容量用于调度，仍应在宿主机运行标准 `eyes-agent`。后续迁移需要为旧版本机检查和资源指标补 `node_id`，并处理 Hub runtime 与宿主机 Agent 的资源去重。
