#!/usr/bin/env python3
"""
eyes — 服务健康检查工具

检查本机 Docker 容器、Systemd 服务、端口、HTTP 端点是否正常运行。
支持邮件通知（通过 himalaya）：异常立即告警 + 每日定时报告。

用法:
    python3 check.py                  # 终端检查
    python3 check.py --json           # JSON 输出
    python3 check.py --watch 10       # 每 10 秒刷新
    python3 check.py --quiet          # 只显示失败项
    python3 check.py --alert          # 有失败才发邮件（每小时 cron 用）
    python3 check.py --report         # 始终发邮件报告（每日 9 点 cron 用）
"""

import argparse
import json
import os
import re
import shutil
import smtplib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML。运行: pip install pyyaml")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
#  Terminal Colors
# ═══════════════════════════════════════════════════════════════

class C:
    RESET    = "\033[0m"
    BOLD     = "\033[1m"
    DIM      = "\033[2m"
    RED      = "\033[31m"
    GREEN    = "\033[32m"
    YELLOW   = "\033[33m"
    CYAN     = "\033[36m"

    @classmethod
    def disable(cls):
        for attr in ("RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW", "CYAN"):
            setattr(cls, attr, "")


# ═══════════════════════════════════════════════════════════════
#  Check Result
# ═══════════════════════════════════════════════════════════════

class Result:
    __slots__ = ("name", "check_type", "ok", "detail")

    def __init__(self, name: str, check_type: str, ok: bool, detail: str):
        self.name = name
        self.check_type = check_type
        self.ok = ok
        self.detail = detail

    def to_dict(self) -> dict:
        return {"name": self.name, "type": self.check_type,
                "ok": self.ok, "detail": self.detail}


# ═══════════════════════════════════════════════════════════════
#  Checkers
# ═══════════════════════════════════════════════════════════════

class Checker(ABC):
    check_type: str = ""

    @abstractmethod
    def check(self, svc: dict) -> Result: ...

    def _ok(self, svc, detail):
        return Result(svc["name"], self.check_type, True, detail)

    def _fail(self, svc, detail):
        return Result(svc["name"], self.check_type, False, detail)


class DockerChecker(Checker):
    check_type = "docker"

    def check(self, svc: dict) -> Result:
        target = svc["target"]
        try:
            r = subprocess.run(
                ["docker", "inspect", "--format",
                 "{{.State.Status}}|{{.State.StartedAt}}", target],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                return self._fail(svc, "容器不存在")
            status, started = r.stdout.strip().split("|", 1)
            if status == "running":
                return self._ok(svc, f"running ({_uptime(started)})")
            return self._fail(svc, status)
        except FileNotFoundError:
            return self._fail(svc, "docker 命令不可用")
        except subprocess.TimeoutExpired:
            return self._fail(svc, "超时")
        except Exception as e:
            return self._fail(svc, str(e))


class SystemdChecker(Checker):
    check_type = "systemd"

    def check(self, svc: dict) -> Result:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", svc["target"]],
                capture_output=True, text=True, timeout=10,
            )
            s = r.stdout.strip()
            if s == "active":
                return self._ok(svc, "active")
            return self._fail(svc, s or "inactive")
        except FileNotFoundError:
            return self._fail(svc, "systemctl 不可用")
        except Exception as e:
            return self._fail(svc, str(e))


class PortChecker(Checker):
    check_type = "port"

    def check(self, svc: dict) -> Result:
        port = int(svc["target"])
        timeout = int(svc.get("timeout", 3))
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            err = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if err == 0:
                return self._ok(svc, "LISTEN")
            return self._fail(svc, "端口未监听")
        except Exception as e:
            return self._fail(svc, str(e))


class HttpChecker(Checker):
    check_type = "http"

    def check(self, svc: dict) -> Result:
        url = svc["url"]
        timeout = int(svc.get("timeout", 5))
        try:
            start = time.monotonic()
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "eyes/1.0")
            resp = urllib.request.urlopen(req, timeout=timeout)
            ms = int((time.monotonic() - start) * 1000)
            code = resp.getcode()
            # 2xx/3xx = OK, 4xx = 警告, 5xx = 失败
            if 200 <= code < 400:
                return self._ok(svc, f"{code} ({ms}ms)")
            elif 400 <= code < 500:
                return self._ok(svc, f"{code} ({ms}ms) ⚠")
            else:
                return self._fail(svc, f"{code} ({ms}ms)")
        except urllib.error.HTTPError as e:
            ms = int((time.monotonic() - start) * 1000)
            if 200 <= e.code < 400:
                return self._ok(svc, f"{e.code} ({ms}ms)")
            elif 400 <= e.code < 500:
                return self._ok(svc, f"{e.code} ({ms}ms) ⚠")
            else:
                return self._fail(svc, f"{e.code} ({ms}ms)")
        except urllib.error.URLError as e:
            return self._fail(svc, f"连接失败: {e.reason}")
        except socket.timeout:
            return self._fail(svc, f"超时 ({timeout}s)")
        except Exception as e:
            return self._fail(svc, str(e))


class CommandChecker(Checker):
    check_type = "command"

    def check(self, svc: dict) -> Result:
        cmd = svc["command"]
        timeout = int(svc.get("timeout", 30))
        try:
            r = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            )
            detail = r.stdout.strip()[:80] or r.stderr.strip()[:80] or f"exit {r.returncode}"
            if r.returncode == 0:
                return self._ok(svc, detail)
            return self._fail(svc, detail)
        except subprocess.TimeoutExpired:
            return self._fail(svc, f"超时 ({timeout}s)")
        except Exception as e:
            return self._fail(svc, str(e))


class CrondChecker(Checker):
    """检查 crontab 中是否存在指定的任务"""
    check_type = "crond"

    def _parse_cron_schedule(self, parts: list[str]) -> str:
        """将 cron 表达式转为可读的调度描述"""
        if len(parts) < 5:
            return "未知"

        minute, hour, day, month, dow = parts[0], parts[1], parts[2], parts[3], parts[4]

        # 每分钟
        if minute == "*" and hour == "*":
            return "每分钟"
        # 每小时
        if minute != "*" and hour == "*":
            return f"每小时第 {minute} 分钟"
        # 每天
        if minute != "*" and hour != "*" and day == "*" and month == "*" and dow == "*":
            return f"每天 {hour}:{minute.zfill(2)}"
        # 每周
        if day == "*" and month == "*" and dow != "*":
            dow_names = {"0": "日", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六"}
            dow_name = dow_names.get(dow, dow)
            return f"每周{ dow_name } {hour}:{minute.zfill(2)}"
        # 其他
        return f"{minute} {hour} {day} {month} {dow}"

    def check(self, svc: dict) -> Result:
        target = svc["target"]  # cron 任务的关键字/命令片段
        try:
            r = subprocess.run(
                ["crontab", "-l"], capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                return self._fail(svc, "无法读取 crontab")

            lines = [l.strip() for l in r.stdout.strip().split("\n")
                     if l.strip() and not l.strip().startswith("#")]

            for line in lines:
                if target in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        schedule = self._parse_cron_schedule(parts[:5])
                        return self._ok(svc, schedule)
                    return self._ok(svc, f"已配置: {line[:60]}")

            return self._fail(svc, f"未找到包含 '{target}' 的 cron 任务")
        except Exception as e:
            return self._fail(svc, str(e))


class PortScanChecker(Checker):
    """安全审计：检查端口是否在白名单中"""
    check_type = "portscan"

    def _build_whitelist(self) -> set[int]:
        """自动构建端口白名单：nginx 路由 + docker 容器 + 系统服务"""
        whitelist = set()

        # 1. 从 nginx 路由获取
        try:
            nginx_dir = "/home/zhuqin/star/gateway/nginx/conf.d"
            for route in _discover_nginx_routes(nginx_dir):
                whitelist.add(route["port"])
        except Exception:
            pass

        # 2. 从运行中的 Docker 容器获取
        try:
            r = subprocess.run(
                ["docker", "ps", "--format", "{{.Ports}}"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                for line in r.stdout.strip().split("\n"):
                    for m in re.finditer(r"(?:0\.0\.0\.0|::|\*):(\d+)->", line):
                        whitelist.add(int(m.group(1)))
        except Exception:
            pass

        # 3. 系统服务端口
        whitelist.update([22, 80])

        # 4. 从白名单配置文件读取例外
        whitelist_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "conf.d", "port_whitelist.txt"
        )
        if os.path.exists(whitelist_file):
            try:
                with open(whitelist_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and line.isdigit():
                            whitelist.add(int(line))
            except Exception:
                pass

        return whitelist

    def _get_port_info(self, port: int) -> tuple[str, str]:
        """获取端口的协议和进程信息，返回 (proto, proc)"""
        # TCP
        try:
            r = subprocess.run(
                ["ss", "-tlnp"], capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                for line in r.stdout.split("\n"):
                    if f":{port} " in line or f":{port}\t" in line:
                        m = re.search(r'users:\(\("([^"]+)"', line)
                        proc = m.group(1) if m else "?"
                        return "tcp", proc
        except Exception:
            pass

        # UDP
        try:
            r = subprocess.run(
                ["ss", "-ulnp"], capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                for line in r.stdout.split("\n"):
                    if f":{port} " in line or f":{port}\t" in line:
                        m = re.search(r'users:\(\("([^"]+)"', line)
                        proc = m.group(1) if m else "?"
                        return "udp", proc
        except Exception:
            pass

        return "", ""

    def check(self, svc: dict) -> Result:
        """检查指定端口是否在白名单中"""
        port = int(svc["target"])
        whitelist = self._build_whitelist()

        proto, proc = self._get_port_info(port)

        if not proto:
            return self._fail(svc, f":{port} 未监听")

        if port in whitelist:
            return self._ok(svc, f":{port} ({proto}) ({proc})")
        else:
            return self._ok(svc, f":{port} ({proto}) ({proc}) ⚠ 未知")


CHECKER_REGISTRY: dict[str, Checker] = {
    cls.check_type: cls()
    for cls in [DockerChecker, SystemdChecker, PortChecker, HttpChecker,
                CommandChecker, CrondChecker, PortScanChecker]
}


# ═══════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════

def _uptime(started_at: str) -> str:
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


# 分类文件名 → 检查类型 + 显示名 映射
# 支持 _nginx_ 前缀的自动生成文件
_CATEGORY_META = {
    "docker":   {"type": "docker",   "title": "Docker 容器"},
    "systemd":  {"type": "systemd",  "title": "Systemd 服务"},
    "http":     {"type": "http",     "title": "HTTP 端点"},
    "port":     {"type": "port",     "title": "端口监听"},
    "command":  {"type": "command",  "title": "自定义命令"},
    "crond":    {"type": "crond",    "title": "Cron 定时任务"},
    "portscan": {"type": "portscan", "title": "端口扫描"},
    # 自动生成的文件 (nginx auto-discover)
    "_nginx_docker": {"type": "docker", "title": "Docker 容器"},
}


# ═══════════════════════════════════════════════════════════════
#  Nginx Auto-Discovery
# ═══════════════════════════════════════════════════════════════

def _parse_nginx_conf(conf_path: str) -> list[dict]:
    """解析单个 nginx conf 文件，提取 server_name → proxy_pass 映射。
    跳过被注释掉的 server block。"""
    routes = []
    try:
        with open(conf_path) as f:
            content = f.read()
    except Exception:
        return routes

    # 移除注释行 (# 开头)
    lines = content.split("\n")
    uncommented = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        uncommented.append(line)
    clean = "\n".join(uncommented)

    # 匹配所有 server block
    # 用正则找到 server { ... } 块
    server_blocks = re.findall(r"server\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", clean)

    for block in server_blocks:
        # 提取 server_name
        sm_match = re.search(r"server_name\s+([^;]+);", block)
        if not sm_match:
            continue
        server_names_raw = sm_match.group(1).strip()
        server_names = [s.strip() for s in server_names_raw.split() if s.strip()]

        # 提取 proxy_pass 端口
        pp_match = re.search(r"proxy_pass\s+http://127\.0\.0\.1:(\d+)", block)
        if not pp_match:
            continue
        port = int(pp_match.group(1))

        # 跳过通配符 catch-all (logwood 通配符)
        is_wildcard = any("*" in sn for sn in server_names)
        if is_wildcard:
            continue

        # 过滤掉纯域名 (如 qzhqzh.com) 只保留子域名
        subdomains = []
        for sn in server_names:
            if ".qzhqzh.com" in sn:
                sub = sn.replace(".qzhqzh.com", "")
                if sub and sub != "*":
                    subdomains.append(sub)
            elif sn != "qzhqzh.com":
                subdomains.append(sn)

        if subdomains:
            routes.append({
                "subdomains": subdomains,
                "port": port,
                "conf_file": os.path.basename(conf_path),
            })

    return routes


def _discover_nginx_routes(nginx_conf_dir: str) -> list[dict]:
    """扫描 nginx conf.d/ 目录，返回所有活跃的子域名路由"""
    routes = []
    conf_dir = Path(nginx_conf_dir)
    if not conf_dir.is_dir():
        return routes

    for f in sorted(conf_dir.glob("*.conf")):
        routes.extend(_parse_nginx_conf(str(f)))

    return routes


def _find_container_for_port(port: int) -> str | None:
    """根据宿主机端口找到对应的 Docker 容器名"""
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}|{{.Ports}}"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return None
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|", 1)
            if len(parts) != 2:
                continue
            name, ports = parts
            # 匹配 0.0.0.0:PORT-> 或 [::]:PORT->
            if re.search(rf"(?:0\.0\.0\.0|::):{port}->", ports):
                return name
    except Exception:
        pass
    return None


def _container_to_display_name(container: str, subdomain: str = "") -> str:
    """容器名转显示名。优先用子域名，否则清理容器名。"""
    if subdomain:
        # 子域名映射为友好名称
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
        }
        if subdomain in mapping:
            return mapping[subdomain]
        return subdomain.replace("-", " ").title()

    # 从容器名推导
    name = container.rstrip("-0123456789")
    name = name.replace("-", " ").replace("_", " ")
    # 首字母大写
    return " ".join(w.capitalize() for w in name.split())


def sync_from_nginx(nginx_conf_dir: str, eyes_conf_dir: str) -> dict:
    """从 nginx 配置自动发现服务，更新 _nginx_docker.yaml。
    返回 {added: [...], removed: [...], unchanged: [...]}"""
    routes = _discover_nginx_routes(nginx_conf_dir)

    # 构建端口 → 子域名映射
    port_to_subdomain = {}
    for r in routes:
        # 取第一个子域名作为主名称
        port_to_subdomain[r["port"]] = r["subdomains"][0]

    # 找到每个端口对应的容器
    docker_entries = []
    port_to_container = {}

    for r in routes:
        port = r["port"]
        sub = port_to_subdomain.get(port, "")
        container = _find_container_for_port(port)
        display = _container_to_display_name(container or "", sub)

        port_to_container[port] = container

        if container:
            docker_entries.append({"name": display, "target": container})

    # 读取旧的自动生成文件，比较变化
    docker_path = os.path.join(eyes_conf_dir, "_nginx_docker.yaml")

    old_docker = _read_auto_entries(docker_path)

    # 生成新文件内容
    new_docker_names = {e["name"] for e in docker_entries}
    old_docker_names = {e["name"] for e in old_docker}

    added = list(new_docker_names - old_docker_names)
    removed = list(old_docker_names - new_docker_names)
    unchanged = list(new_docker_names & old_docker_names)

    # 写入文件
    _write_auto_entries(docker_path, docker_entries, "Docker 容器 (Nginx 自动发现)")

    return {
        "added": added,
        "removed": removed,
        "unchanged": unchanged,
        "routes": routes,
        "containers": port_to_container,
    }


def _read_auto_entries(path: str) -> list[dict]:
    """读取自动生成的 yaml 文件"""
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            items = yaml.safe_load(f)
        return items if isinstance(items, list) else []
    except Exception:
        return []


def _write_auto_entries(path: str, entries: list[dict], header: str):
    """写入自动生成的 yaml 文件"""
    lines = [
        f"# {header}",
        f"# ⚠ 此文件由 eyes --sync 自动生成，请勿手动编辑",
        f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for e in entries:
        if "target" in e:
            lines.append(f'- {{ name: "{e["name"]}", target: {e["target"]} }}')
        elif "url" in e:
            lines.append(f'- {{ name: "{e["name"]}", url: "{e["url"]}", timeout: {e.get("timeout", 5)} }}')
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))


def _load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(f"{C.RED}错误: 配置文件不存在: {path}{C.RESET}")
        sys.exit(1)
    with open(p) as f:
        return yaml.safe_load(f)


def _load_service_groups(config: dict, config_dir: str) -> list[dict]:
    """从 conf.d/ 目录加载所有服务分组，同类型自动合并"""
    conf_dir = Path(config_dir)
    if not conf_dir.is_dir():
        print(f"{C.RED}错误: 配置目录不存在: {conf_dir}{C.RESET}")
        sys.exit(1)

    # 按类型收集服务
    type_services: dict[str, list] = {}
    type_title: dict[str, str] = {}

    for f in sorted(conf_dir.glob("*.yaml")):
        category = f.stem  # 文件名去掉 .yaml
        meta = _CATEGORY_META.get(category)
        if not meta:
            print(f"  {C.YELLOW}跳过未知分类: {f.name} "
                  f"(可用: {', '.join(_CATEGORY_META)}){C.RESET}")
            continue

        with open(f) as fh:
            items = yaml.safe_load(fh)
        if not items:
            continue

        svc_type = meta["type"]
        # 给每个 service 注入 type
        for svc in items:
            svc["type"] = svc_type

        if svc_type not in type_services:
            type_services[svc_type] = []
            type_title[svc_type] = meta["title"]
        type_services[svc_type].extend(items)

    # 转换为 groups 列表，按层级排序
    groups = []
    for svc_type in ["docker", "systemd", "crond", "command", "http", "port", "portscan"]:
        if svc_type in type_services:
            groups.append({
                "group": type_title[svc_type],
                "services": type_services[svc_type],
            })

    return groups


def _display_width(s: str) -> int:
    return sum(2 if ord(ch) > 0x7F else 1 for ch in s)


# ═══════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════

def run_checks(groups: list[dict]) -> list[dict]:
    groups_out = []
    for group in groups:
        results: list[Result] = []
        for svc in group.get("services", []):
            svc_type = svc.get("type", "")
            checker = CHECKER_REGISTRY.get(svc_type)
            if not checker:
                results.append(Result(
                    svc.get("name", "?"), svc_type, False,
                    f"未知类型: {svc_type}，可用: {', '.join(CHECKER_REGISTRY)}",
                ))
                continue
            results.append(checker.check(svc))
        groups_out.append({"group": group.get("group", ""), "services": results})
    return groups_out


def collect_stats(groups: list[dict]) -> dict:
    total = passed = failed = 0
    failures = []
    for g in groups:
        for s in g["services"]:
            total += 1
            if s.ok:
                passed += 1
            else:
                failed += 1
                failures.append({"group": g["group"], "name": s.name,
                                 "detail": s.detail})
    return {"total": total, "passed": passed, "failed": failed,
            "failures": failures, "healthy": failed == 0}


# ═══════════════════════════════════════════════════════════════
#  Reporter — Terminal
# ═══════════════════════════════════════════════════════════════

def report_terminal(groups: list[dict], quiet: bool = False) -> bool:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = passed = failed = 0

    print()
    print(f"  {C.BOLD}{C.CYAN}{'═' * 48}{C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}   👁  Service Health Report{C.RESET}"
          f"  {C.DIM}{now_str}{C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}{'═' * 48}{C.RESET}")

    for g in groups:
        svcs = g["services"]
        g_pass = sum(1 for s in svcs if s.ok)
        g_total = len(svcs)
        total += g_total
        passed += g_pass
        failed += g_total - g_pass

        color = C.GREEN if g_pass == g_total else C.RED
        print(f"\n  {C.BOLD}{g['group']}  ({g_pass}/{g_total}){C.RESET}  {color}{'✓' if g_pass == g_total else '✗'}{C.RESET}")
        print(f"  {C.DIM}{'─' * 48}{C.RESET}")

        for s in svcs:
            if quiet and s.ok:
                continue
            icon = f"{C.GREEN}✓{C.RESET}" if s.ok else f"{C.RED}✗{C.RESET}"
            dc = C.DIM if s.ok else C.RED
            pad = max(1, 20 - _display_width(s.name))
            print(f"  {icon} {s.name}{' ' * pad}{dc}{s.detail}{C.RESET}")

    print(f"\n  {C.BOLD}{C.CYAN}{'═' * 48}{C.RESET}")
    if failed == 0:
        print(f"  {C.BOLD}{C.GREEN}  TOTAL: {passed}/{total}  "
              f"✓ All systems operational{C.RESET}")
    else:
        print(f"  {C.BOLD}{C.RED}  TOTAL: {passed}/{total}  "
              f"✗ {failed} service(s) down!{C.RESET}")
    print(f"  {C.BOLD}{C.CYAN}{'═' * 48}{C.RESET}\n")
    return failed == 0


def report_json(groups: list[dict]):
    stats = collect_stats(groups)
    out_groups = []
    for g in groups:
        out_groups.append({"name": g["group"],
                           "services": [s.to_dict() for s in g["services"]]})
    print(json.dumps({
        "timestamp": datetime.now().isoformat(),
        **stats, "groups": out_groups,
    }, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════
#  Reporter — Email (via himalaya)
# ═══════════════════════════════════════════════════════════════

def _build_html(groups: list[dict], stats: dict, mode: str) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_alert = mode == "alert"
    title = "⚠ 服务异常告警" if is_alert else "📊 每日服务健康报告"
    header_color = "#e74c3c" if is_alert else "#2ecc71"

    rows = ""
    for g in groups:
        svcs = g["services"]
        g_pass = sum(1 for s in svcs if s.ok)
        g_total = len(svcs)
        status_icon = "✓" if g_pass == g_total else "✗"
        rows += f'<tr><td colspan="3" style="background:#f8f9fa;padding:10px 16px;font-weight:bold;color:#333;border-bottom:1px solid #dee2e6">{g["group"]}  ({g_pass}/{g_total})  {status_icon}</td></tr>'
        for s in g["services"]:
            if is_alert and s.ok:
                continue
            icon = "✅" if s.ok else "❌"
            color = "#27ae60" if s.ok else "#e74c3c"
            rows += (
                f'<tr>'
                f'<td style="padding:6px 16px;border-bottom:1px solid #f0f0f0">{icon}</td>'
                f'<td style="padding:6px 16px;border-bottom:1px solid #f0f0f0">{s.name}</td>'
                f'<td style="padding:6px 16px;border-bottom:1px solid #f0f0f0;color:{color}">{s.detail}</td>'
                f'</tr>'
            )

    fail_summary = ""
    if stats["failures"]:
        items = "".join(
            f"<li><b>{f['name']}</b> ({f['group']}): {f['detail']}</li>"
            for f in stats["failures"]
        )
        fail_summary = f'<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:6px;padding:12px 16px;margin:16px 0"><b>⚠ 异常项：</b><ul style="margin:8px 0 0 0">{items}</ul></div>'

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#333">
<div style="background:{header_color};color:#fff;padding:20px;border-radius:8px 8px 0 0;text-align:center">
  <h2 style="margin:0">{title}</h2>
  <p style="margin:8px 0 0 0;opacity:0.9">{now_str}</p>
</div>
<div style="border:1px solid #dee2e6;border-top:none;border-radius:0 0 8px 8px;overflow:hidden">
<div style="padding:16px;text-align:center;font-size:18px">
  <span style="color:#27ae60;font-weight:bold">{stats['passed']}</span> /
  <span>{stats['total']}</span>
  {"<span style='color:#e74c3c;margin-left:12px'>✗ " + str(stats['failed']) + " 项异常</span>" if stats['failed'] else "<span style='color:#27ae60;margin-left:12px'>✓ 全部正常</span>"}
</div>
{fail_summary}
<table style="width:100%;border-collapse:collapse;font-size:14px">
{rows}
</table>
</div>
<div style="text-align:center;padding:16px;color:#999;font-size:12px">eyes — 服务健康检查工具</div>
</body></html>"""


def _build_text(groups: list[dict], stats: dict, mode: str) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_alert = mode == "alert"
    title = "⚠ 服务异常告警" if is_alert else "📊 每日服务健康报告"
    lines = [title, now_str, "",
             f"总数: {stats['total']}  通过: {stats['passed']}  失败: {stats['failed']}", ""]
    for g in groups:
        svcs = g["services"]
        g_pass = sum(1 for s in svcs if s.ok)
        g_total = len(svcs)
        status_icon = "✓" if g_pass == g_total else "✗"
        lines.append(f"[{g['group']}  ({g_pass}/{g_total})  {status_icon}]")
        for s in g["services"]:
            if is_alert and s.ok:
                continue
            icon = "✓" if s.ok else "✗"
            lines.append(f"  {icon} {s.name}: {s.detail}")
        lines.append("")
    return "\n".join(lines)


def _build_mml(email_cfg: dict, groups: list[dict], stats: dict, mode: str, to_addrs: list[str]) -> str:
    """构建 himalaya MML 格式的邮件（From/To/Subject + MIME multipart）"""
    is_alert = mode == "alert"
    subject = "⚠ 服务异常告警" if is_alert else "📊 每日服务健康报告"
    subject += f" [{stats['passed']}/{stats['total']}]"

    from_addr = email_cfg.get("from", "")
    to_line = ", ".join(to_addrs)
    text_body = _build_text(groups, stats, mode)
    html_body = _build_html(groups, stats, mode)

    boundary = "eyes-boundary-" + str(int(time.time()))
    headers = ""
    if from_addr:
        headers += f"From: {from_addr}\n"
    return (
        f"{headers}"
        f"To: {to_line}\n"
        f"Subject: {subject}\n"
        f"MIME-Version: 1.0\n"
        f"Content-Type: multipart/alternative; boundary={boundary}\n"
        f"\n"
        f"--{boundary}\n"
        f"Content-Type: text/plain; charset=utf-8\n"
        f"\n"
        f"{text_body}\n"
        f"\n"
        f"--{boundary}\n"
        f"Content-Type: text/html; charset=utf-8\n"
        f"\n"
        f"{html_body}\n"
        f"\n"
        f"--{boundary}--\n"
    )


def _send_via_smtp(email_cfg: dict, msg: MIMEMultipart, from_addr: str, to_addrs: list[str]) -> bool:
    """通过 SMTP 直连发送"""
    import ssl
    smtp_cfg = email_cfg.get("smtp", {})
    host = smtp_cfg.get("host", "")
    port = int(smtp_cfg.get("port", 465))
    use_ssl = smtp_cfg.get("ssl", True)
    user = smtp_cfg.get("user", "")
    password = smtp_cfg.get("password", "")

    if not password:
        print(f"  {C.RED}SMTP 密码未配置 (email.smtp.password){C.RESET}")
        return False

    if use_ssl:
        ctx = ssl.create_default_context()
        server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.ehlo()
    server.login(user, password)
    server.sendmail(from_addr, to_addrs, msg.as_string())
    server.quit()
    return True


def _send_via_himalaya(msg: MIMEMultipart) -> bool:
    """通过 himalaya CLI 发送"""
    himalaya = shutil.which("himalaya")
    if not himalaya:
        print(f"  {C.RED}himalaya 未安装{C.RESET}")
        return False
    # himalaya template send 读 MML 格式，需要 From + Subject + 正文
    raw = msg.as_string()
    r = subprocess.run(
        ["himalaya", "template", "send"],
        input=raw, capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        return True
    err = r.stderr.strip() or r.stdout.strip() or f"exit {r.returncode}"
    print(f"  {C.RED}himalaya 发送失败: {err}{C.RESET}")
    return False


def send_email(config: dict, groups: list[dict], stats: dict, mode: str):
    """发送邮件通知"""
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled"):
        print(f"  {C.YELLOW}邮件未启用，跳过发送{C.RESET}")
        return False

    to_addrs = email_cfg.get("to", [])
    if not to_addrs:
        print(f"  {C.RED}收件人未配置 (email.to){C.RESET}")
        return False

    from_addr = email_cfg.get("from", "")
    method = email_cfg.get("method", "smtp")

    is_alert = mode == "alert"
    subject = "⚠ 服务异常告警" if is_alert else "📊 每日服务健康报告"
    subject += f" [{stats['passed']}/{stats['total']}]"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    if from_addr:
        msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(_build_text(groups, stats, mode), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(groups, stats, mode), "html", "utf-8"))

    try:
        if method == "smtp":
            ok = _send_via_smtp(email_cfg, msg, from_addr, to_addrs)
        elif method == "himalaya":
            ok = _send_via_himalaya(msg)
        else:
            print(f"  {C.RED}未知邮件方式: {method} (可选: smtp / himalaya){C.RESET}")
            return False

        if ok:
            print(f"  {C.GREEN}✓ 邮件已发送至: {', '.join(to_addrs)}{C.RESET}")
        return ok
    except Exception as e:
        print(f"  {C.RED}✗ 邮件发送异常: {e}{C.RESET}")
        return False


# ═══════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="eyes — 服务健康检查工具")
    ap.add_argument("-c", "--config",
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                         "config.yaml"),
                    help="配置文件路径")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    ap.add_argument("-w", "--watch", type=int, metavar="SEC", help="持续监控刷新")
    ap.add_argument("-q", "--quiet", action="store_true", help="只显示失败项")
    ap.add_argument("--alert", action="store_true",
                    help="有失败才发邮件（每小时 cron）")
    ap.add_argument("--report", action="store_true",
                    help="始终发邮件报告（每日 9 点 cron）")
    ap.add_argument("--sync", action="store_true",
                    help="从 nginx 配置自动发现服务，同步监控列表")
    ap.add_argument("--nginx-conf-dir",
                    default="/home/zhuqin/star/gateway/nginx/conf.d",
                    help="nginx conf.d 目录路径")
    args = ap.parse_args()

    if args.json or not sys.stdout.isatty():
        C.disable()

    config = _load_config(args.config)

    # 配置目录: 优先用绝对路径，否则相对配置文件所在目录
    conf_dir = config.get("conf_dir", "conf.d")
    config_base = os.path.dirname(os.path.abspath(args.config))
    if not os.path.isabs(conf_dir):
        conf_dir = os.path.join(config_base, conf_dir)

    # ─── Nginx 自动发现 ───────────────────────────────────────
    if args.sync:
        print(f"\n  {C.CYAN}🔄 扫描 nginx 配置: {args.nginx_conf_dir}{C.RESET}")
        result = sync_from_nginx(args.nginx_conf_dir, conf_dir)

        if result["added"]:
            print(f"  {C.GREEN}+ 新增 {len(result['added'])} 个服务:{C.RESET}")
            for name in result["added"]:
                print(f"    + {name}")
        if result["removed"]:
            print(f"  {C.YELLOW}- 移除 {len(result['removed'])} 个服务:{C.RESET}")
            for name in result["removed"]:
                print(f"    - {name}")
        if not result["added"] and not result["removed"]:
            print(f"  {C.GREEN}✓ 监控列表无变化 ({len(result['unchanged'])} 个服务){C.RESET}")

        # 映射表
        print(f"\n  {C.DIM}nginx 路由 → 容器映射:{C.RESET}")
        for r in result["routes"]:
            port = r["port"]
            container = result["containers"].get(port, "?")
            subs = ", ".join(r["subdomains"])
            print(f"    {subs}.qzhqzh.com → :{port} → {container or '(无容器)'}")
        print()

    service_groups = _load_service_groups(config, conf_dir)

    def once(mode: str = "terminal") -> bool:
        groups = run_checks(service_groups)
        stats = collect_stats(groups)

        if mode == "terminal":
            if args.json:
                report_json(groups)
            else:
                report_terminal(groups, quiet=args.quiet)
        elif mode == "alert":
            report_terminal(groups)
            if not stats["healthy"]:
                print(f"  {C.YELLOW}检测到异常，发送告警邮件...{C.RESET}")
                send_email(config, groups, stats, "alert")
            else:
                print(f"  {C.GREEN}全部正常，无需告警{C.RESET}")
        elif mode == "report":
            report_terminal(groups)
            print(f"  {C.CYAN}发送每日报告邮件...{C.RESET}")
            send_email(config, groups, stats, "report")

        return stats["healthy"]

    if args.alert:
        ok = once("alert")
        sys.exit(0 if ok else 1)
    elif args.report:
        once("report")
        sys.exit(0)
    elif args.watch:
        try:
            while True:
                if not args.json:
                    print("\033[2J\033[H", end="", flush=True)
                once()
                if not args.json:
                    print(f"  {C.DIM}每 {args.watch}s 刷新，Ctrl+C 退出{C.RESET}")
                time.sleep(args.watch)
        except KeyboardInterrupt:
            print()
            sys.exit(0)
    else:
        sys.exit(0 if once() else 1)


if __name__ == "__main__":
    main()
