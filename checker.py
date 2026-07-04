#!/usr/bin/env python3
"""eyes — 检查引擎模块

提供检查函数供 Web 应用调用。
- Docker: 通过 docker.sock API 检查
- Systemd/Cron: 通过 agent API 检查
- HTTP/Port: 直接检查
"""

import json
import os
import socket
import subprocess
import time
import urllib.request
import urllib.error
import http.client
from datetime import datetime, timezone


# Agent URL 缓存
_agent_url = None


def _get_agent_url():
    """获取 agent URL"""
    global _agent_url
    if _agent_url is None:
        from models import get_setting
        _agent_url = get_setting("agent_url", "http://host.docker.internal:9091")
    return _agent_url


def _query_docker_api(endpoint):
    """查询 Docker API（通过 docker.sock）"""
    sock_path = "/var/run/docker.sock"
    if not os.path.exists(sock_path):
        return None
    
    try:
        import socket as sock_module
        s = sock_module.socket(sock_module.AF_UNIX, sock_module.SOCK_STREAM)
        s.connect(sock_path)
        conn = http.client.HTTPConnection("localhost")
        conn.sock = s
        conn.request("GET", endpoint)
        response = conn.getresponse()
        data = json.loads(response.read().decode())
        conn.close()
        return data
    except Exception:
        return None


def _query_agent_api(endpoint, timeout=5):
    """查询 Agent API"""
    agent_url = _get_agent_url()
    try:
        url = f"{agent_url}{endpoint}"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode())
    except Exception:
        return None


def check_docker(target):
    """检查 Docker 容器状态"""
    # 方法1: 通过 docker.sock API
    data = _query_docker_api("/containers/json")
    if data is not None:
        for container in data:
            name = container.get("Names", [""])[0].lstrip("/")
            if name == target:
                state = container.get("State", "")
                status = container.get("Status", "")
                if state == "running":
                    return True, f"running ({status})"
                return False, state or status
        return False, "容器不存在"
    
    # 方法2: 回退到命令行
    try:
        import subprocess
        r = subprocess.run(
            ["docker", "inspect", "--format",
             "{{.State.Status}}|{{.State.StartedAt}}", target],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return False, "容器不存在"
        status, started = r.stdout.strip().split("|", 1)
        if status == "running":
            uptime = _uptime(started)
            return True, f"running ({uptime})"
        return False, status
    except FileNotFoundError:
        return False, "docker 不可用"
    except Exception as e:
        return False, str(e)


def check_systemd(target):
    """检查 Systemd 服务状态"""
    # 通过 agent API
    services = _query_agent_api("/api/systemd")
    if services and isinstance(services, list):
        service_name = target.replace(".service", "")
        for svc in services:
            if svc.get("name") == service_name:
                active = svc.get("active", "unknown")
                if active == "active":
                    return True, "active"
                return False, active
        return False, "未找到服务"
    
    # 回退到命令行
    try:
        import subprocess
        r = subprocess.run(
            ["systemctl", "is-active", target],
            capture_output=True, text=True, timeout=10,
        )
        s = r.stdout.strip()
        if s == "active":
            return True, "active"
        return False, s or "inactive"
    except Exception as e:
        return False, str(e)


def check_port(target, timeout=3):
    """检查端口是否监听"""
    port = int(target)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        err = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if err == 0:
            return True, "LISTEN"
        return False, "端口未监听"
    except Exception as e:
        return False, str(e)


def check_http(url, timeout=5):
    """检查 HTTP 端点"""
    start = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "eyes/1.0")
        resp = urllib.request.urlopen(req, timeout=timeout)
        ms = int((time.monotonic() - start) * 1000)
        code = resp.getcode()
        if 200 <= code < 400:
            return True, f"{code} ({ms}ms)"
        elif 400 <= code < 500:
            return True, f"{code} ({ms}ms) ⚠"
        else:
            return False, f"{code} ({ms}ms)"
    except urllib.error.HTTPError as e:
        ms = int((time.monotonic() - start) * 1000)
        if 200 <= e.code < 400:
            return True, f"{e.code} ({ms}ms)"
        elif 400 <= e.code < 500:
            return True, f"{e.code} ({ms}ms) ⚠"
        else:
            return False, f"{e.code} ({ms}ms)"
    except urllib.error.URLError as e:
        return False, f"连接失败: {e.reason}"
    except socket.timeout:
        return False, f"超时 ({timeout}s)"
    except Exception as e:
        return False, str(e)


def check_command(command, timeout=30):
    """检查自定义命令"""
    try:
        r = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout,
        )
        detail = r.stdout.strip()[:80] or r.stderr.strip()[:80] or f"exit {r.returncode}"
        if r.returncode == 0:
            return True, detail
        return False, detail
    except subprocess.TimeoutExpired:
        return False, f"超时 ({timeout}s)"
    except Exception as e:
        return False, str(e)


def check_crond(target):
    """检查 crontab 中是否存在指定任务"""
    # 通过 agent API
    crontab_data = _query_agent_api("/api/crontab")
    if crontab_data and isinstance(crontab_data, dict):
        for user, tasks in crontab_data.items():
            if isinstance(tasks, list):
                for task in tasks:
                    if target in task:
                        return True, f"已配置 ({user})"
        return False, "未找到任务"
    
    # 回退到命令行
    try:
        import subprocess
        r = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return False, "无法读取 crontab"

        lines = [l.strip() for l in r.stdout.strip().split("\n")
                 if l.strip() and not l.strip().startswith("#")]

        for line in lines:
            if target in line:
                return True, "已配置"

        return False, f"未找到任务"
    except Exception as e:
        return False, str(e)


def run_check(item_type, target):
    """运行单个检查项"""
    checkers = {
        "docker": check_docker,
        "systemd": check_systemd,
        "port": check_port,
        "http": check_http,
        "command": check_command,
        "crond": check_crond,
    }
    
    checker = checkers.get(item_type)
    if not checker:
        return False, f"未知类型: {item_type}"
    
    return checker(target)


def run_all_checks(items):
    """运行所有检查项
    
    Args:
        items: [{"id": ..., "type": ..., "name": ..., "target": ...}]
    
    Returns:
        [{"id": ..., "type": ..., "name": ..., "ok": ..., "detail": ...}]
    """
    results = []
    for item in items:
        if not item.get("enabled", True):
            continue
        
        ok, detail = run_check(item["type"], item["target"])
        results.append({
            "id": item["id"],
            "type": item["type"],
            "name": item["name"],
            "ok": ok,
            "detail": detail,
        })
    
    return results


def _uptime(started_at: str) -> str:
    """计算运行时间"""
    try:
        clean = started_at.split(".")[0] + "Z"
        start = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%SZ")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        sec = int((now - start).total_seconds())
        if sec < 60:   return f"{sec}s"
        if sec < 3600:  return f"{sec // 60}m"
        if sec < 86400: return f"{sec // 3600}h{(sec % 3600) // 60}m"
        return f"{sec // 86400}d{(sec % 86400) // 3600}h"
    except Exception:
        return "?"


if __name__ == "__main__":
    # 测试
    print("测试 Docker 检查 (通过 API)...")
    ok, detail = check_docker("eyes-web")
    print(f"  结果: {'✓' if ok else '✗'} {detail}")
    
    print("\n测试 Agent 连接...")
    data = _query_agent_api("/api/info")
    if data:
        print(f"  ✓ {data.get('hostname')}")
    else:
        print("  ✗ 连接失败")
