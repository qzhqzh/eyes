#!/usr/bin/env python3
"""eyes — 服务自动扫描模块"""

import os
import re
import subprocess
import json
import urllib.request
from pathlib import Path


def scan_docker_containers():
    """扫描运行中的 Docker 容器（通过 docker.sock API）"""
    containers = []
    try:
        # 通过 docker.sock 的 HTTP API 查询
        sock_path = "/var/run/docker.sock"
        if os.path.exists(sock_path):
            import http.client
            conn = http.client.HTTPConnection("localhost")
            conn.sock = None
            # 使用 unix socket
            import socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(sock_path)
            conn.sock = sock
            
            conn.request("GET", "/containers/json")
            response = conn.getresponse()
            data = json.loads(response.read().decode())
            
            for container in data:
                name = container.get("Names", [""])[0].lstrip("/")
                image = container.get("Image", "")
                state = container.get("State", "")
                
                if state == "running":
                    display_name = _generate_display_name(name)
                    containers.append({
                        "type": "docker",
                        "name": display_name,
                        "target": name,
                        "source": "docker"
                    })
            
            conn.close()
        else:
            # 回退到命令行
            r = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}|{{.Image}}|{{.Status}}"],
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                for line in r.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("|", 2)
                    if len(parts) >= 3:
                        name, image, status = parts
                        display_name = _generate_display_name(name)
                        containers.append({
                            "type": "docker",
                            "name": display_name,
                            "target": name,
                            "source": "docker"
                        })
    except Exception as e:
        print(f"扫描 Docker 失败: {e}")
    return containers


def scan_nginx_routes(nginx_conf_dir=None):
    """从 nginx 配置扫描服务（通过反向代理发现后端服务）"""
    nginx_conf_dir = nginx_conf_dir or os.environ.get(
        "EYES_NGINX_CONF_DIR", "/nginx-conf.d"
    )
    routes = []
    conf_dir = Path(nginx_conf_dir)
    if not conf_dir.is_dir():
        return routes

    for conf_file in sorted(conf_dir.glob("*.conf")):
        try:
            with open(conf_file) as f:
                content = f.read()
            
            # 移除注释
            lines = content.split("\n")
            uncommented = [l for l in lines if not l.strip().startswith("#")]
            clean = "\n".join(uncommented)
            
            # 找到 server 块
            server_blocks = re.findall(r"server\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", clean)
            
            for block in server_blocks:
                # 提取 server_name
                sm_match = re.search(r"server_name\s+([^;]+);", block)
                if not sm_match:
                    continue
                server_names = sm_match.group(1).strip().split()
                
                # 提取 proxy_pass
                pp_match = re.search(r"proxy_pass\s+http://127\.0\.0\.1:(\d+)", block)
                if not pp_match:
                    continue
                port = int(pp_match.group(1))
                
                # 跳过通配符
                if any("*" in sn for sn in server_names):
                    continue
                
                # 提取子域名
                subdomains = []
                for sn in server_names:
                    if ".qzhqzh.com" in sn:
                        sub = sn.replace(".qzhqzh.com", "")
                        if sub and sub != "*":
                            subdomains.append(sub)
                    elif sn != "qzhqzh.com":
                        subdomains.append(sn)
                
                if subdomains:
                    # 找到对应的容器
                    container = _find_container_for_port(port)
                    if container:
                        display_name = _subdomain_to_name(subdomains[0])
                        routes.append({
                            "type": "docker",
                            "name": display_name,
                            "target": container,
                            "source": "nginx",
                            "subdomain": subdomains[0],
                            "port": port
                        })
        except Exception:
            continue
    
    return routes


def scan_from_agent(agent_url="http://host.docker.internal:9091"):
    """从宿主机 agent 获取信息"""
    results = {
        "systemd": [],
        "crond": [],
        "system": {}
    }
    
    try:
        # 获取 systemd 服务
        req = urllib.request.Request(f"{agent_url}/api/systemd")
        resp = urllib.request.urlopen(req, timeout=5)
        services = json.loads(resp.read().decode())
        
        if isinstance(services, list):
            for svc in services:
                if svc.get("active") in ("active", "failed"):
                    results["systemd"].append({
                        "type": "systemd",
                        "name": _service_display_name(svc["name"]),
                        "target": f"{svc['name']}.service",
                        "source": "agent"
                    })
        
        # 获取 crontab
        req = urllib.request.Request(f"{agent_url}/api/crontab")
        resp = urllib.request.urlopen(req, timeout=5)
        crontab = json.loads(resp.read().decode())
        
        if isinstance(crontab, dict):
            for user, tasks in crontab.items():
                for task in tasks:
                    name = _cron_display_name(task)
                    results["crond"].append({
                        "type": "crond",
                        "name": f"{name} ({user})",
                        "target": task[:50],
                        "source": "agent"
                    })
        
        # 获取系统信息
        req = urllib.request.Request(f"{agent_url}/api/info")
        resp = urllib.request.urlopen(req, timeout=5)
        results["system"] = json.loads(resp.read().decode())
        
    except Exception as e:
        print(f"连接 agent 失败: {e}")
    
    return results


def scan_all(agent_url=None):
    """执行完整扫描"""
    results = {
        "docker": [],
        "systemd": [],
        "crond": [],
    }
    
    # 扫描 Docker 容器
    results["docker"] = scan_docker_containers()
    
    # 扫描 Nginx 路由（与 Docker 合并去重）
    nginx_routes = scan_nginx_routes()
    docker_targets = {item["target"] for item in results["docker"]}
    for route in nginx_routes:
        if route["target"] not in docker_targets:
            results["docker"].append(route)
            docker_targets.add(route["target"])
    
    # 从 agent 获取宿主机信息
    if agent_url:
        agent_data = scan_from_agent(agent_url)
        results["systemd"] = agent_data.get("systemd", [])
        results["crond"] = agent_data.get("crond", [])
    
    return results


def _generate_display_name(container_name):
    """从容器名生成友好的显示名"""
    # 移除数字后缀
    name = container_name.rstrip("-0123456789")
    # 替换分隔符
    name = name.replace("-", " ").replace("_", " ")
    # 首字母大写
    return " ".join(w.capitalize() for w in name.split())


def _subdomain_to_name(subdomain):
    """从子域名生成友好的显示名"""
    mapping = {
        "echome": "EchoMe Web",
        "echomeapi": "EchoMe API",
        "hub": "Hub Site",
        "tm": "TrafficMeter",
        "tr": "Converter",
        "vault": "Vaultwarden",
        "inventory": "Inventory",
        "design": "Design Preview",
        "box": "Box",
        "cpvhub": "Cpvhub",
        "biocs": "BioCS",
        "www": "Www",
    }
    if subdomain in mapping:
        return mapping[subdomain]
    return subdomain.replace("-", " ").title()


def _find_container_for_port(port):
    """根据端口找到对应的容器名"""
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Ports}}"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("|", 1)
                if len(parts) != 2:
                    continue
                name, ports = parts
                if re.search(rf"(?:0\.0\.0\.0|::):{port}->", ports):
                    return name
    except Exception:
        pass
    return None


def _service_display_name(service):
    """生成服务的显示名"""
    names = {
        "docker": "Docker Engine",
        "ssh": "SSH Server",
        "sshd": "SSH Server",
        "nginx": "Nginx",
        "cron": "Cron Daemon",
        "crond": "Cron Daemon",
        "systemd-resolved": "DNS Resolver",
        "NetworkManager": "Network Manager",
        "dbus": "D-Bus",
        "polkit": "PolicyKit",
    }
    return names.get(service, service.replace("-", " ").replace("_", " ").title())


def _cron_display_name(cmd):
    """从 cron 命令生成友好的显示名"""
    if "eyes" in cmd.lower():
        return "eyes 监控"
    if "backup" in cmd.lower():
        return "备份任务"
    if "log" in cmd.lower() or "rotate" in cmd.lower():
        return "日志轮转"
    if "certbot" in cmd.lower() or "ssl" in cmd.lower():
        return "证书续期"
    if "docker" in cmd.lower():
        return "Docker 任务"
    # 截取命令的前部分
    parts = cmd.split("/")
    if len(parts) > 1:
        return parts[-1][:20]
    return cmd[:20]


if __name__ == "__main__":
    import sys
    agent_url = sys.argv[1] if len(sys.argv) > 1 else None
    results = scan_all(agent_url)
    print(json.dumps(results, indent=2, ensure_ascii=False))
