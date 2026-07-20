# 安全设计

## 信任边界

系统至少包含四个身份主体：

- Hub 操作者。
- Consumer Agent 或 API 用户。
- Eyes Node Agent。
- 具体 Workload。

这些主体不能共享一个全能 Token。查询资源、提交任务、调度绑定、节点上报和特权操作需要分别授权。

## 当前实现进入多节点前必须改变的点

- 当前 Agent 监听 `0.0.0.0:9091` 且没有认证；目标模式默认不开放入站接口。
- 当前 Agent 以 root 运行；目标模式拆成非特权 Core 与最小权限 Helper。
- 当前 Web Session Secret 和默认密码在源码中；目标模式使用环境/Secret 文件、随机 Secret 和密码哈希。
- Docker Socket 即使以只读文件挂载，Docker API 仍具有高权限风险；不能把它作为多节点远程执行边界。
- 当前 `command` 检查支持 `shell=True`；它不能直接复用为远程执行协议。远程 shell 必须通过独立 ShellSession 授权和审计。

## 节点身份

### Bootstrap

- 安装命令只携带短期、单次注册 Token。
- Agent 本地生成私钥并提交公钥证明。
- Hub 签发节点证书或短期凭据，记录证书指纹、注册来源和允许标签。

### 常态认证

- 推荐 mTLS，节点证书短期轮换。
- Hub 校验节点身份后再绑定 `node_id`，不信任请求体自报身份。
- 节点撤销、证书过期和密钥轮换必须可操作。
- 小型部署先使用 Eyes 内建 CA；规模和多信任域复杂度增加后再评估 SPIFFE/SPIRE。

## 授权模型

建议动作级权限：

```text
node.read
resource.read
workload.submit
workload.cancel.own
workload.cancel.any
node.policy.write
service.restart
node.shell.open
node.shell.sudo
node.shell.break_glass
node.shell.recording.read
lease.bind
artifact.read
audit.read
```

- Consumer Agent 不能调用 `lease.bind`。
- `workload.submit` 不隐含 `node.shell.open`，`node.shell.open` 也不隐含 sudo/root。
- Node Agent 只能更新自己的状态和 Lease 执行结果。
- Scheduler 可以绑定 Claim，但不能修改节点探测的硬件事实。
- Privileged Helper 只接受本机 Core，并再次检查动作 allowlist。

## 工作负载隔离

第一执行后端建议使用 rootless OCI 容器；确需 rootful 时单独标记高风险节点和策略。

至少限制：

- CPU、内存、PID、临时磁盘和执行时限。
- 默认无特权、只读根文件系统、最小 Linux capabilities。
- 默认禁止挂载宿主机路径、Docker Socket 和设备。
- 网络默认拒绝或按策略允许目的地。
- Secret 只在任务运行时注入，不写入 Workload、日志或 Artifact 元数据。
- 镜像使用 digest；后续加入签名验证和 registry allowlist。

AI Agent 传入的文本、代码、URL 和文件都按不可信输入处理。

## 节点维护 Shell

根据权限允许直接 shell，但必须把它视为独立的高风险控制面：

- 推荐使用短期 OpenSSH Certificate 或一次性会话凭据，不在 Hub 保存长期 SSH 私钥或节点密码。
- 每次会话绑定 actor、node、reason、权限级别、签发时间、到期时间和空闲超时。
- 节点使用专用维护用户；sudo 通过独立策略控制，默认只允许命令 allowlist。
- 自动化 Agent 获得 shell 权限时，应限制目标节点、命令、目录、网络、并发和最大时长；高风险提权可要求人工审批。
- 元数据审计为强制项。是否记录完整输入输出按策略决定，因为完整录屏可能捕获密码、Token 和敏感数据。
- break-glass root 会话使用独立权限、短 TTL、显式理由和醒目标记，并在结束后触发审计提醒。
- 会话关闭或过期后立即撤销凭据；节点离线恢复后不能自动恢复旧 shell。

“直接 shell”描述操作能力，不要求暴露公网 SSH 端口。网络可通过 WireGuard/Tailscale/Headscale 直连；授权仍由 Eyes Hub 统一签发和记录。

## Lease 安全

- Lease 带期限、目标节点、资源边界和不可回退的 fencing token。
- 节点执行前校验签名、到期时间、当前 token 和本地资源状态。
- Hub 失联不应让新任务无限启动；已有任务按 workload policy 决定继续、暂停或终止。
- Lease 释放和 Artifact 上传完成是不同事件，避免上传失败导致资源永久占用。

## 审计

以下事件必须保存结构化审计：

- 节点注册、撤销和证书轮换。
- 节点标签、策略和可调度资源变更。
- Workload 提交、调度解释、Claim、Lease、执行和取消。
- 特权动作和策略拒绝。
- Artifact 访问和 Secret 使用记录，但不记录 Secret 内容。

审计记录包含 actor、action、target、decision、reason、request_id、timestamp 和不可变摘要。

## 安全失效原则

- Hub 状态过期：停止新绑定，不猜测资源仍可用。
- 节点策略不确定：拒绝执行并上报原因。
- Artifact 校验失败：标记失败，不把未验证结果交给 Consumer Agent。
- 时钟明显漂移：限制 Lease，要求校时并告警。
- 版本不兼容：节点保留观察能力，但禁止不兼容的执行命令。

动态资源系统需要严格区分 scheduler、driver 和使用者权限。Kubernetes DRA 也为 Claim binding 与 driver status 更新使用独立最小权限，这一原则可作为 Eyes 的授权参考：[DRA Hardening Guide](https://kubernetes.io/docs/concepts/security/hardening-guide/dynamic-resource-allocation/)。
