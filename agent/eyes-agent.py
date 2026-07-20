#!/usr/bin/env python3
"""eyes-agent — 宿主机轻量 Agent

节点模式主动连接 Eyes Hub；旧版 HTTP 模式保留用于兼容现有部署。

用法：
    python3 eyes-agent.py --mode node --hub-url https://eyes.example.com
    python3 eyes-agent.py --mode legacy-server --port 9091

安装为 systemd 服务：
    sudo sh install.sh
    sudo editor /etc/eyes/agent.env
    sudo systemctl enable --now eyes-agent
"""

import argparse
import hmac
import json
import os
import platform
import shutil
import socket
import subprocess
import re
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

from node_client import ExponentialBackoff, HubClient, HubClientError, NodeStateStore


AGENT_VERSION = "0.2.0"
PROTOCOL_VERSION = "eyes.node.v1"


def get_systemd_services():
    """获取 systemd 服务状态"""
    services = []
    if not shutil.which("systemctl"):
        return services
    try:
        r = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                parts = line.split(None, 4)
                if len(parts) >= 4:
                    name = parts[0].replace(".service", "")
                    load = parts[1]
                    active = parts[2]
                    sub = parts[3]
                    desc = parts[4] if len(parts) > 4 else ""
                    
                    # 只返回有意义的服务
                    if active in ("active", "failed", "inactive") and name not in ("-", ""):
                        services.append({
                            "name": name,
                            "active": active,
                            "sub": sub,
                            "description": desc
                        })
    except Exception as e:
        return {"error": str(e)}
    return services


def get_service_status(service_name):
    """获取单个服务的详细状态"""
    try:
        r = subprocess.run(
            ["systemctl", "is-active", f"{service_name}.service"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def get_crontab(user=None):
    """获取 crontab 任务"""
    tasks = []
    try:
        cmd = ["crontab", "-l"]
        if user:
            cmd = ["crontab", "-l", "-u", user]
        
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                tasks.append(line)
    except Exception as e:
        return {"error": str(e)}
    return tasks


def get_cron_all_users():
    """获取所有用户的 crontab"""
    result = {}
    import os
    import pwd
    
    for user in pwd.getpwall():
        username = user.pw_name
        tasks = get_crontab(username)
        if tasks and not isinstance(tasks, dict):  # 没有错误
            result[username] = tasks
    
    # 系统 crontab
    try:
        with open("/etc/crontab") as f:
            system_cron = []
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    system_cron.append(line)
            if system_cron:
                result["system"] = system_cron
    except Exception:
        pass
    
    return result


def get_system_info():
    """获取系统基本信息"""
    info = {}
    
    # 主机名
    try:
        with open("/etc/hostname") as f:
            info["hostname"] = f.read().strip()
    except Exception:
        info["hostname"] = "unknown"
    
    # 运行时间
    try:
        with open("/proc/uptime") as f:
            uptime_secs = float(f.read().split()[0])
            if uptime_secs < 3600:
                info["uptime"] = f"{int(uptime_secs/60)}m"
            elif uptime_secs < 86400:
                info["uptime"] = f"{int(uptime_secs/3600)}h{int((uptime_secs%3600)/60)}m"
            else:
                info["uptime"] = f"{int(uptime_secs/86400)}d{int((uptime_secs%86400)/3600)}h"
    except Exception:
        info["uptime"] = "unknown"
    
    # 负载
    try:
        with open("/proc/loadavg") as f:
            loads = f.read().split()[:3]
            info["load"] = " ".join(loads)
    except Exception:
        info["load"] = "unknown"
    
    info["timestamp"] = datetime.now().isoformat()
    
    return info


def full_scan():
    """完整扫描"""
    return {
        "system": get_system_info(),
        "systemd": get_systemd_services(),
        "crontab": get_cron_all_users(),
    }


def get_boot_id():
    """返回本次系统启动的稳定标识。"""
    try:
        with open("/proc/sys/kernel/random/boot_id") as f:
            return f.read().strip()
    except Exception:
        return f"fallback-{platform.node()}"


def discover_capabilities():
    """发现当前节点可安全声明的基础能力。"""
    capabilities = [
        {
            "name": "eyes.io/system.observe",
            "version": "v1",
            "health": "ready",
        }
    ]
    if shutil.which("systemctl"):
        capabilities.append(
            {"name": "eyes.io/systemd.read", "version": "v1", "health": "ready"}
        )
    docker_socket = "/var/run/docker.sock"
    if shutil.which("docker") and os.access(docker_socket, os.R_OK | os.W_OK):
        capabilities.append(
            {
                "name": "eyes.io/executor.container",
                "version": "v1alpha1",
                "health": "ready",
                "attributes": {"runtime": "docker"},
            }
        )
    if shutil.which("nvidia-smi"):
        capabilities.append(
            {"name": "nvidia.com/gpu", "version": "v1", "health": "ready"}
        )
    if shutil.which("wg"):
        capabilities.append(
            {"name": "eyes.io/wireguard.read", "version": "v1", "health": "ready"}
        )
    return capabilities


def collect_inventory():
    """采集低频节点事实，不包含凭据和敏感环境变量。"""
    addresses = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            address = info[4][0]
            if address not in addresses:
                addresses.append(address)
    except Exception:
        pass

    return {
        "system": get_system_info(),
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "network": {"addresses": addresses},
        "systemd": get_systemd_services(),
        "capabilities": discover_capabilities(),
    }


def collect_resources():
    """采集可调度资源容量和当前基础观测值。"""
    memory_total = 0
    memory_available = 0
    try:
        with open("/proc/meminfo") as f:
            values = {}
            for line in f:
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0]) * 1024
            memory_total = values.get("MemTotal", 0)
            memory_available = values.get("MemAvailable", 0)
    except Exception:
        pass

    disk = shutil.disk_usage("/")
    cpu_count = os.cpu_count() or 1
    return {
        "cpu": {
            "capacity_millis": cpu_count * 1000,
            "allocatable_millis": cpu_count * 1000,
            "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
        },
        "memory": {
            "capacity_bytes": memory_total,
            "allocatable_bytes": memory_total,
            "available_bytes": memory_available,
        },
        "filesystem": {
            "root": {
                "capacity_bytes": disk.total,
                "available_bytes": disk.free,
            }
        },
    }


def _parse_roles(value):
    return [role.strip() for role in value.split(",") if role.strip()]


def _parse_labels(value):
    if not value:
        return {}
    labels = json.loads(value)
    if not isinstance(labels, dict):
        raise ValueError("--labels 必须是 JSON object")
    return labels


def run_node_agent(args):
    """运行主动出站的 Hub 节点循环。"""
    if not args.hub_url:
        raise ValueError("node 模式需要 --hub-url 或 EYES_HUB_URL")

    state_store = NodeStateStore(args.state_dir)
    identity = state_store.load_or_create()
    hostname = socket.gethostname()
    metadata = {
        "hostname": hostname,
        "display_name": args.display_name or hostname,
        "roles": _parse_roles(args.roles),
        "labels": _parse_labels(args.labels),
        "agent_version": AGENT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
    }

    client = HubClient(
        args.hub_url,
        credential=identity.credential,
        node_id=identity.node_id,
        timeout=args.request_timeout,
        user_agent=f"eyes-agent/{AGENT_VERSION}",
        allow_insecure_http=args.allow_insecure_http,
    )
    if not identity.enrolled:
        if not args.enroll_token:
            raise ValueError("首次注册需要 --enroll-token 或 EYES_ENROLL_TOKEN")
        identity = state_store.prepare_enrollment()
        enrollment = client.enroll(
            args.enroll_token,
            identity.node_id,
            node_token=identity.credential,
            metadata=metadata,
        )
        credential = enrollment.get("node_token")
        if not credential or not hmac.compare_digest(credential, identity.credential):
            raise RuntimeError("Hub 注册响应缺少或改变了 node_token")
        identity = state_store.mark_enrolled()
        client.credential = identity.credential
        print(f"eyes-agent 已注册节点: {identity.node_id}")

    boot_id = get_boot_id()
    backoff = ExponentialBackoff(initial=1, maximum=60)
    next_snapshot_at = 0.0
    command_cursor = 0

    while True:
        try:
            now_monotonic = time.monotonic()
            client.heartbeat(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "agent_version": AGENT_VERSION,
                    "boot_id": boot_id,
                    "sequence": time.monotonic_ns(),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                    "conditions": [{"type": "Ready", "status": True}],
                    "active_lease_ids": [],
                }
            )

            if now_monotonic >= next_snapshot_at:
                observed_at = datetime.now(timezone.utc).isoformat()
                client.put_inventory(
                    {
                        "generation": time.time_ns(),
                        "observed_at": observed_at,
                        "payload": collect_inventory(),
                    }
                )
                client.put_resources(
                    {
                        "generation": time.time_ns(),
                        "observed_at": observed_at,
                        "payload": collect_resources(),
                    }
                )
                next_snapshot_at = now_monotonic + args.snapshot_interval

            command_response = client.get_commands(cursor=command_cursor, wait=0)
            commands = command_response.get("commands", [])
            if commands:
                print(f"收到 {len(commands)} 个待处理命令；当前版本仅完成通道，不执行命令")
            else:
                command_cursor = int(command_response.get("cursor", command_cursor))

            backoff.reset()
            if args.once:
                return
            time.sleep(args.heartbeat_interval)
        except HubClientError as exc:
            if args.once:
                raise
            delay = backoff.next_delay()
            print(f"连接 Hub 失败: {exc}; {delay:.1f}s 后重试")
            time.sleep(delay)


class AgentHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/": self.handle_index,
            "/api/systemd": self.handle_systemd,
            "/api/crontab": self.handle_crontab,
            "/api/info": self.handle_info,
            "/api/scan": self.handle_scan,
        }
        
        handler = routes.get(self.path)
        if handler:
            handler()
        else:
            self.send_error(404)
    
    def handle_index(self):
        self.send_json({
            "service": "eyes-agent",
            "version": "1.0",
            "endpoints": ["/api/systemd", "/api/crontab", "/api/info", "/api/scan"]
        })
    
    def handle_systemd(self):
        self.send_json(get_systemd_services())
    
    def handle_crontab(self):
        self.send_json(get_cron_all_users())
    
    def handle_info(self):
        self.send_json(get_system_info())
    
    def handle_scan(self):
        self.send_json(full_scan())
    
    def send_json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    
    def log_message(self, format, *args):
        # 简化日志
        pass


def run_legacy_server(args):
    """运行旧版入站 HTTP Agent，供现有单机部署过渡。"""
    server = HTTPServer((args.host, args.port), AgentHandler)
    print(f"eyes-agent legacy 模式启动: http://{args.host}:{args.port}")
    print("  /api/systemd  - Systemd 服务")
    print("  /api/crontab  - 定时任务")
    print("  /api/info     - 系统信息")
    print("  /api/scan     - 完整扫描")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
        server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="eyes-agent 宿主机代理")
    parser.add_argument(
        "--mode",
        choices=("node", "legacy-server"),
        default=os.environ.get("EYES_AGENT_MODE", "legacy-server"),
        help="运行模式 (默认 legacy-server，设置 hub-url 时自动使用 node)",
    )
    parser.add_argument("--port", type=int, default=9091, help="监听端口 (默认 9091)")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    parser.add_argument("--hub-url", default=os.environ.get("EYES_HUB_URL", ""))
    parser.add_argument("--enroll-token", default=os.environ.get("EYES_ENROLL_TOKEN", ""))
    parser.add_argument("--state-dir", default=os.environ.get("EYES_STATE_DIR", "/var/lib/eyes"))
    parser.add_argument("--display-name", default=os.environ.get("EYES_DISPLAY_NAME", ""))
    parser.add_argument("--roles", default=os.environ.get("EYES_NODE_ROLES", "worker"))
    parser.add_argument("--labels", default=os.environ.get("EYES_NODE_LABELS", "{}"))
    parser.add_argument("--heartbeat-interval", type=int, default=30)
    parser.add_argument("--snapshot-interval", type=int, default=300)
    parser.add_argument("--request-timeout", type=float, default=30)
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        default=os.environ.get("EYES_ALLOW_INSECURE_HTTP", "").lower()
        in {"1", "true", "yes"},
        help="允许连接非本机的明文 HTTP Hub（仅限受控测试网络）",
    )
    parser.add_argument("--once", action="store_true", help="只执行一次上报后退出")
    args = parser.parse_args()

    if args.mode == "node" or args.hub_url:
        run_node_agent(args)
    else:
        run_legacy_server(args)


if __name__ == "__main__":
    main()
