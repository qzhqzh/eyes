# Eyes 文档中心

Eyes 想做的事情很直接：把你拥有的机器、服务和 AI 能力连接到一个 Hub，让你先看清资源，再逐步把它们安全地交给 Agent 使用。

如果你第一次接触项目，建议先阅读仓库根目录的 [README](../README.md) 并启动 Hub。登录后可以从四个页面开始：

| 入口 | 适合解决的问题 |
| --- | --- |
| `/` 服务状态 | Hub 本机的服务和资源现在是否正常？ |
| `/fleet` Fleet 节点 | 哪些机器在线，各自有什么资源和能力？ |
| `/domains` 域名管理 | 网关代理了哪些域名，它们能否正常访问？ |
| `/assets` 资产管理 | 哪些模型和 Context7 账号可供 Agent 使用？ |

## 按你的目标阅读

### 我想先用起来

- [README 快速开始](../README.md#快速启动-hub)：配置密码、启动 Hub、访问页面。
- [观测作用域与统计口径](observability-scopes.md)：为什么服务状态和 Fleet 的数字不一样，以及各卡片何时更新。
- [资产管理与 Agent 服务聚合](asset-management.md)：怎样看模型状态、配置 Context7，并让 Agent 接入 MCP。

### 我想把更多机器接进来

- [产品愿景与边界](product-vision.md)：Eyes 解决什么问题，哪些能力属于当前版本，哪些仍是目标。
- [Hub-Agent 协议](protocol.md)：节点注册、心跳、资源上报和命令拉取。
- [安全设计](security.md)：节点身份、权限分离、维护 Shell 和凭据边界。

### 我要参与设计或开发

- [总体架构](architecture.md)：Hub、节点、执行和数据组件怎样协作。
- [资源与调度模型](resource-model.md)：Capability、Workload、ResourceClaim 和 Lease 的含义。
- [实现状态](implementation-status.md)：已经落地、仍是骨架和暂未启用的能力。
- [演进路线](roadmap.md)：按阶段推进的功能和验收标准。

## 当前设计共识

- 非 Hub 节点以无界面的 `eyes-agent` 系统服务运行，并主动出站连接 Hub。
- Hub 汇总所有接入节点的联通状态、资源、能力和服务；Hub 所在物理机器也应通过标准 Agent 上报。
- AI Agent 通过统一 API 或 MCP 使用被授权的资源，不直接获得节点密码或长期 SSH Key。
- 普通资源使用和宿主机维护权限分离。未来的直接 Shell 会是短期、可审计的高权限能力，不是默认入口。
- Eyes 不自研 VPN，也不替代 Kubernetes、Nomad 或 Ray；它负责发现、整合和连接已有资源。

## 当前版本的边界

目前可以稳定使用的是健康观测、节点注册与上报、Fleet 汇总、域名探测、模型目录和 Context7 MCP 聚合。Workload、调度、Lease、节点命令执行和维护 Shell 仍未形成完整执行闭环。

Context7 账号池是可选功能：代码已经支持多账号切换、额度恢复和查询缓存，但真实账号需由部署者在本机 Secret 中配置后验收。未配置账号不会影响 Hub、Fleet、域名或模型目录。

## 文档维护规则

- 已落地行为以代码和测试为准，目标设计必须明确标注为“规划”或“尚未实现”。
- 影响协议、持久化数据或安全边界的改动，需要同时写清兼容策略。
- 不在文档、示例、页面或提交中放置密码、Token、模型 Key 和 Context7 Key。
- 架构发生实质变化时，同步更新 EchoMe 的 `eyes` 项目记忆。
