#!/usr/bin/env python3
"""eyes-agent — 宿主机轻量 Agent

运行在宿主机，提供系统信息给 eyes 容器。

用法：
    python3 agent.py              # 默认监听 9091
    python3 agent.py --port 8080  # 指定端口

安装为 systemd 服务：
    sudo cp eyes-agent.service /etc/systemd/system/
    sudo systemctl enable --now eyes-agent
"""

import argparse
import json
import subprocess
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime


def get_systemd_services():
    """获取 systemd 服务状态"""
    services = []
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


def main():
    parser = argparse.ArgumentParser(description="eyes-agent 宿主机代理")
    parser.add_argument("--port", type=int, default=9091, help="监听端口 (默认 9091)")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认 0.0.0.0)")
    args = parser.parse_args()
    
    server = HTTPServer((args.host, args.port), AgentHandler)
    print(f"eyes-agent 启动: http://{args.host}:{args.port}")
    print(f"  /api/systemd  - Systemd 服务")
    print(f"  /api/crontab  - 定时任务")
    print(f"  /api/info     - 系统信息")
    print(f"  /api/scan     - 完整扫描")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
        server.shutdown()


if __name__ == "__main__":
    main()
