#!/usr/bin/env python3
"""eyes — Flask Web 应用"""

import os
import functools
import fcntl
import hmac
import secrets
import subprocess
import re
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from apscheduler.schedulers.background import BackgroundScheduler
from models import (
    init_db, init_default_settings, get_setting, set_setting, get_all_settings,
    get_check_items, get_all_check_items, add_check_item, update_check_item, delete_check_item,
    update_item_status, get_check_results, import_from_yaml, replace_check_results,
    replace_check_results_for_types, save_resource_metrics, get_resource_metrics,
    get_latest_resource_metric, clear_old_metrics, DB_PATH, claim_operation_cooldown
)
from checker import run_check, run_all_checks
from bark import send_bark_alert, send_bark_recovery
from email_sender import send_email_alert, send_email_report, send_test_email
from scanner import scan_all
from fleet import init_fleet_db, ensure_local_hub_node
from hub_node import refresh_local_hub_node
from hub_api import hub_api
from network_status import collect_wireguard_with_agent, mounted_filesystem_type

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
secure_config_required = os.environ.get("EYES_REQUIRE_SECURE_CONFIG") == "1"
configured_secret = os.environ.get("EYES_SECRET_KEY", "")
configured_web_password = os.environ.get("EYES_WEB_PASSWORD", "")
configured_enroll_token = os.environ.get("EYES_HUB_ENROLL_TOKEN", "")
secure_values = (configured_secret, configured_web_password, configured_enroll_token)
if secure_config_required and (
    not configured_secret
    or not configured_web_password
    or len(configured_secret) < 32
    or len(configured_web_password) < 12
    or (configured_enroll_token and len(configured_enroll_token) < 24)
    or any(value.lower().startswith("replace-with-") for value in secure_values)
):
    raise RuntimeError(
        "set non-placeholder EYES_SECRET_KEY (32+ chars), EYES_WEB_PASSWORD "
        "(12+ chars), and optional EYES_HUB_ENROLL_TOKEN (24+ chars)"
    )
app.secret_key = configured_secret or secrets.token_urlsafe(32)

# 初始化数据库
init_db()
init_default_settings()

# 多节点控制面基础表和版本化 API
init_fleet_db()
ensure_local_hub_node()
try:
    refresh_local_hub_node()
except Exception as exc:
    app.logger.warning("initial Hub runtime observation failed: %s", exc)
app.register_blueprint(hub_api)

# 配置目录
CONF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "conf.d")


def collect_stats():
    """采集系统资源并保存"""
    stats = {}
    
    # CPU 使用率
    try:
        r = subprocess.run(
            "top -bn1 | grep 'Cpu(s)'",
            capture_output=True, text=True, shell=True, timeout=5
        )
        if r.returncode == 0 and r.stdout:
            match = re.search(r'(\d+\.?\d*)\s*id', r.stdout)
            if match:
                idle = float(match.group(1))
                stats['cpu'] = round(100 - idle, 1)
            else:
                stats['cpu'] = -1
        else:
            stats['cpu'] = -1
    except Exception as e:
        print(f"CPU error: {e}")
        stats['cpu'] = -1
    
    # 内存使用率
    try:
        r = subprocess.run(
            "free -m | grep Mem",
            capture_output=True, text=True, shell=True, timeout=5
        )
        if r.returncode == 0 and r.stdout:
            parts = r.stdout.split()
            if len(parts) >= 3:
                total = int(parts[1])
                used = int(parts[2])
                stats['memory'] = round(used / total * 100, 1)
                stats['memory_used'] = f"{used}MB"
                stats['memory_total'] = f"{total}MB"
            else:
                stats['memory'] = -1
        else:
            stats['memory'] = -1
    except Exception as e:
        print(f"Memory error: {e}")
        stats['memory'] = -1
    
    # 硬盘使用率
    try:
        r = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    stats['disk'] = parts[4].replace('%', '')
                    stats['disk_used'] = parts[2]
                    stats['disk_total'] = parts[1]
                else:
                    stats['disk'] = -1
            else:
                stats['disk'] = -1
        else:
            stats['disk'] = -1
    except Exception as e:
        print(f"Disk error: {e}")
        stats['disk'] = -1
    
    # NAS 盘使用率
    try:
        stats['nas'] = -1
        nas_path = os.environ.get("EYES_NAS_PATH", "/mnt/nas")
        allowed_nas_types = {
            value.strip() for value in os.environ.get(
                "EYES_NAS_FS_TYPES", "cifs,nfs,nfs4,smb3,fuse.sshfs"
            ).split(",") if value.strip()
        }
        filesystem_type = mounted_filesystem_type(nas_path)
        if filesystem_type in allowed_nas_types:
            r = subprocess.run(
                ["df", "-h", nas_path], capture_output=True, text=True, timeout=5
            )
            lines = r.stdout.strip().split("\n")
            if r.returncode == 0 and len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    stats['nas'] = parts[4].replace('%', '')
                    stats['nas_used'] = parts[2]
                    stats['nas_total'] = parts[1]
                else:
                    stats['nas'] = -1
        else:
            stats['nas'] = -1
    except Exception as e:
        print(f"NAS error: {e}")
        stats['nas'] = -1
    
    # 保存到数据库
    try:
        save_resource_metrics(
            stats.get('cpu', -1),
            stats.get('memory', -1),
            stats.get('disk', -1),
            stats.get('nas', -1),
            stats.get('memory_used', ''),
            stats.get('memory_total', ''),
            stats.get('disk_used', ''),
            stats.get('disk_total', ''),
            stats.get('nas_used', ''),
            stats.get('nas_total', '')
        )
    except Exception as e:
        print(f"Save metrics error: {e}")
    
    return stats


_health_check_thread_lock = threading.Lock()
_service_scan_thread_lock = threading.Lock()
SERVICE_SCAN_COOLDOWN_SECONDS = 60
HEALTH_GROUP_TYPES = {
    "docker": {"docker"},
    "systemd": {"systemd"},
    "crond": {"crond"},
    "other": {"http", "port", "command"},
}
HEALTH_GROUP_DEFAULT_INTERVALS = {
    "docker": 600,
    "systemd": 1800,
    "crond": 1800,
    "other": 600,
}


def collect_health_checks(item_types=None, wait=False):
    """Run the configured Hub-local checks and persist their latest result."""
    if not _health_check_thread_lock.acquire(blocking=wait):
        return {"success": False, "busy": True, "error": "health check is already running"}
    lock_file = None
    try:
        lock_file = open(f"{DB_PATH}.health.lock", "a", encoding="utf-8")
        try:
            lock_flags = fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB
            fcntl.flock(lock_file.fileno(), lock_flags)
        except BlockingIOError:
            return {"success": False, "busy": True, "error": "health check is already running"}

        items = get_check_items()
        requested_types = set(item_types or [])
        enabled_items = [
            item for item in items
            if item["enabled"] and (not requested_types or item["type"] in requested_types)
        ]
        results = run_all_checks(enabled_items)
        failures = []
        for result in results:
            if not result["ok"]:
                failures.append({"name": result["name"], "detail": result["detail"]})
        if requested_types:
            replace_check_results_for_types(results, requested_types)
        else:
            replace_check_results(results)

        settings = get_all_settings()
        if settings.get("bark_enabled") == "1" and failures:
            send_bark_alert(
                failures,
                server=settings.get("bark_server", "https://api.day.app"),
                key=settings.get("bark_key", ""),
                group=settings.get("bark_group", "Dev"),
            )
        return {
            "success": True,
            "total": len(results),
            "passed": sum(1 for result in results if result["ok"]),
            "failed": len(failures),
            "failures": failures,
            "types": sorted(requested_types),
        }
    finally:
        if lock_file is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
        _health_check_thread_lock.release()


# 启动定时任务调度器
scheduler = BackgroundScheduler()
interval = int(get_setting("resource_collect_interval", "300"))
scheduler.add_job(id='collect_resource_metrics', func=collect_stats, trigger='interval', seconds=interval, replace_existing=True)
if os.environ.get("EYES_ENABLE_SCHEDULED_CHECKS") == "1":
    for offset, (group, item_types) in enumerate(HEALTH_GROUP_TYPES.items(), start=1):
        seconds = int(get_setting(
            f"check_interval_{group}", str(HEALTH_GROUP_DEFAULT_INTERVALS[group])
        ))
        if seconds < 60:
            raise RuntimeError(f"check_interval_{group} must be at least 60 seconds")
        scheduler.add_job(
            id=f'collect_health_{group}',
            func=collect_health_checks,
            args=[item_types, True],
            trigger='interval',
            seconds=seconds,
            next_run_time=datetime.now() + timedelta(seconds=offset * 5),
            coalesce=True,
            max_instances=1,
            replace_existing=True,
        )
scheduler.add_job(id='clear_old_metrics', func=clear_old_metrics, trigger='interval', hours=24)
scheduler.add_job(
    id='refresh_local_hub_node',
    func=refresh_local_hub_node,
    trigger='interval',
    seconds=30,
    replace_existing=True,
)
scheduler.start()


def login_required(f):
    """登录验证装饰器"""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.route("/login", methods=["GET", "POST"])
def login():
    """登录页面"""
    if request.method == "POST":
        password = request.form.get("password", "")
        stored_password = configured_web_password or get_setting("web_password", "")
        if stored_password and hmac.compare_digest(password, stored_password):
            session["logged_in"] = True
            return redirect(url_for("index"))
        return render_template("login.html", error="密码错误")
    return render_template("login.html")


@app.route("/logout")
def logout():
    """退出登录"""
    session.pop("logged_in", None)
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    """主页"""
    settings = get_all_settings()
    items = get_check_items()
    results = get_check_results()
    
    # 按类型分组
    grouped_items = {}
    for item in items:
        item_type = item["type"]
        if item_type not in grouped_items:
            grouped_items[item_type] = []
        grouped_items[item_type].append(item)
    
    # 结果映射
    result_map = {r["item_id"]: r for r in results}
    
    return render_template("index.html",
                         settings=settings,
                         grouped_items=grouped_items,
                         result_map=result_map)


@app.route("/fleet")
@login_required
def fleet_view():
    """多节点 Fleet 页面。"""
    return render_template("fleet.html", active_page="fleet")


@app.route("/api/settings", methods=["GET"])
@login_required
def get_settings():
    """获取所有设置"""
    settings = get_all_settings()
    if os.environ.get("EYES_AGENT_URL"):
        settings["agent_url"] = os.environ["EYES_AGENT_URL"]
    return jsonify(settings)


@app.route("/api/settings", methods=["POST"])
@login_required
def update_settings():
    """更新设置"""
    data = request.json
    for key, value in data.items():
        set_setting(key, str(value))
    return jsonify({"success": True})


@app.route("/api/items", methods=["GET"])
@login_required
def list_items():
    """获取监控项列表"""
    item_type = request.args.get("type")
    include_deprecated = request.args.get("include_deprecated") == "1"
    if include_deprecated:
        return jsonify(get_all_check_items(item_type))
    return jsonify(get_check_items(item_type))


@app.route("/api/items", methods=["POST"])
@login_required
def create_item():
    """创建监控项"""
    data = request.json
    item_id = add_check_item(data["type"], data["name"], data["target"])
    return jsonify({"id": item_id, "success": True})


@app.route("/api/items/<int:item_id>", methods=["PUT"])
@login_required
def update_item(item_id):
    """更新监控项"""
    data = request.json
    update_check_item(item_id,
                     name=data.get("name"),
                     target=data.get("target"),
                     enabled=data.get("enabled"))
    return jsonify({"success": True})


@app.route("/api/items/<int:item_id>/status", methods=["PUT"])
@login_required
def change_item_status(item_id):
    """更新监控项状态（active/deprecated）"""
    data = request.json
    update_item_status(item_id, data.get("status", "active"))
    return jsonify({"success": True})


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
@login_required
def remove_item(item_id):
    """删除监控项"""
    delete_check_item(item_id)
    return jsonify({"success": True})


@app.route("/api/check", methods=["POST"])
@login_required
def run_checks():
    """运行检查"""
    group = request.args.get("group") or (request.get_json(silent=True) or {}).get("group")
    if group:
        item_types = HEALTH_GROUP_TYPES.get(group)
        if item_types is None:
            return jsonify({"error": "unknown health group"}), 400
        result = collect_health_checks(item_types)
        result["group"] = group
        return jsonify(result), 409 if result.get("busy") else 200

    group_results = []
    for group_name, item_types in HEALTH_GROUP_TYPES.items():
        result = collect_health_checks(item_types, wait=True)
        result["group"] = group_name
        group_results.append(result)
    return jsonify({
        "success": all(result.get("success") for result in group_results),
        "total": sum(result.get("total", 0) for result in group_results),
        "passed": sum(result.get("passed", 0) for result in group_results),
        "failed": sum(result.get("failed", 0) for result in group_results),
        "groups": group_results,
    })


@app.route("/api/results", methods=["GET"])
@login_required
def list_results():
    """获取检查结果"""
    item_type = request.args.get("type")
    results = get_check_results()
    if item_type:
        results = [result for result in results if result["item_type"] == item_type]
    return jsonify(results)


@app.route("/api/check-intervals", methods=["GET", "POST"])
@login_required
def check_intervals():
    """Get or update the automatic refresh interval for a dashboard group."""
    if request.method == "POST":
        if os.environ.get("EYES_ENABLE_SCHEDULED_CHECKS") != "1":
            return jsonify({"error": "scheduled health checks are disabled"}), 409
        data = request.get_json(silent=True) or {}
        group = data.get("group")
        if group not in HEALTH_GROUP_TYPES:
            return jsonify({"error": "unknown health group"}), 400
        try:
            seconds = int(data.get("minutes")) * 60
        except (TypeError, ValueError):
            return jsonify({"error": "minutes must be an integer"}), 400
        if seconds < 60 or seconds > 86400:
            return jsonify({"error": "interval must be between 1 minute and 24 hours"}), 400
        set_setting(f"check_interval_{group}", str(seconds))
        job = scheduler.get_job(f"collect_health_{group}")
        if job:
            scheduler.reschedule_job(
                f"collect_health_{group}", trigger="interval", seconds=seconds
            )
        return jsonify({"success": True, "group": group, "seconds": seconds})

    intervals = {
        group: int(get_setting(
            f"check_interval_{group}", str(HEALTH_GROUP_DEFAULT_INTERVALS[group])
        ))
        for group in HEALTH_GROUP_TYPES
    }
    intervals["resources"] = int(get_setting("resource_collect_interval", "300"))
    intervals["scheduled_checks_enabled"] = (
        os.environ.get("EYES_ENABLE_SCHEDULED_CHECKS") == "1"
    )
    return jsonify(intervals)


@app.route("/api/scan", methods=["POST"])
@login_required
def scan_services():
    """扫描系统中的服务"""
    if not _service_scan_thread_lock.acquire(blocking=False):
        return jsonify({"error": "service scan is already running", "retry_after_seconds": 60}), 429
    try:
        claimed, retry_after = claim_operation_cooldown(
            "service_scan", SERVICE_SCAN_COOLDOWN_SECONDS
        )
        if not claimed:
            return jsonify(
                {"error": "service scan cooldown is active", "retry_after_seconds": retry_after}
            ), 429

        settings = get_all_settings()
        agent_url = os.environ.get("EYES_AGENT_URL") or settings.get("agent_url", "")
        results = scan_all(agent_url if agent_url else None)

        existing_items = get_check_items()
        existing_targets = {item["target"] for item in existing_items}
        added_count = 0
        for items in results.values():
            for item in items:
                if item["target"] not in existing_targets:
                    add_check_item(item["type"], item["name"], item["target"])
                    added_count += 1
                    existing_targets.add(item["target"])

        return jsonify({
            "success": True,
            "added": added_count,
            "cooldown_seconds": SERVICE_SCAN_COOLDOWN_SECONDS,
            "details": {
                "docker": len(results.get("docker", [])),
                "systemd": len(results.get("systemd", [])),
                "crond": len(results.get("crond", []))
            }
        })
    finally:
        _service_scan_thread_lock.release()


@app.route("/api/test-bark", methods=["POST"])
@login_required
def test_bark():
    """测试 Bark 推送"""
    settings = get_all_settings()
    from bark import send_bark
    result = send_bark(
        title="eyes 测试",
        body="这是一条测试消息",
        server=settings.get("bark_server", "https://api.day.app"),
        key=settings.get("bark_key", ""),
        group=settings.get("bark_group", "Dev")
    )
    return jsonify({"success": result})


@app.route("/api/system-stats", methods=["GET", "POST"])
@login_required
def system_stats():
    """获取实时系统资源统计，保留原有 API 语义。"""
    stats = collect_stats()
    
    # 运行时间
    try:
        r = subprocess.run(
            ["uptime", "-p"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0 and r.stdout:
            stats['uptime'] = r.stdout.strip().replace('up ', '')
    except Exception as e:
        print(f"Uptime error: {e}")
        stats['uptime'] = 'unknown'
    
    return jsonify(stats)


@app.route("/api/system-stats/latest", methods=["GET"])
@login_required
def latest_system_stats():
    """获取后台最近一次采集的资源快照。"""
    stats = get_latest_resource_metric() or collect_stats()
    return jsonify(stats)


@app.route("/api/resource-metrics", methods=["GET"])
@login_required
def resource_metrics():
    """获取资源历史数据"""
    hours = request.args.get('hours', 24, type=int)
    metrics = get_resource_metrics(hours)
    return jsonify(metrics)


@app.route("/api/resource-collect-interval", methods=["GET", "POST"])
@login_required
def resource_collect_interval():
    """获取/设置资源采集频率（分钟）"""
    if request.method == "GET":
        seconds = int(get_setting("resource_collect_interval", "300"))
        return jsonify({"seconds": seconds, "minutes": seconds // 60})
    
    data = request.json
    minutes = data.get('minutes', 5)
    
    # 更新设置
    seconds = int(minutes) * 60
    set_setting("resource_collect_interval", str(seconds))
    
    # 更新调度器
    scheduler.reschedule_job('collect_resource_metrics', trigger='interval', seconds=seconds)
    
    return jsonify({"success": True, "seconds": seconds, "minutes": int(minutes)})


@app.route("/api/network-speed", methods=["GET"])
@login_required
def network_speed():
    """测试到外部目标点的 TCP 连通延迟"""
    import socket
    
    targets = {
        'google':  ('dns.google.com', 53),
        'github':  ('github.com', 443),
        'gpt':     ('api.openai.com', 443),
        'youtube': ('youtube.com', 443),
    }
    
    results = {}
    for name, (host, port) in targets.items():
        try:
            import time
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            t0 = time.monotonic()
            s.connect((host, port))
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            s.close()
            results[name] = {'ok': True, 'ms': elapsed_ms}
        except Exception:
            results[name] = {'ok': False, 'ms': None}
    
    return jsonify(results)


@app.route("/api/last-check-time", methods=["GET"])
@login_required
def last_check_time():
    """获取最近一次检查时间"""
    from models import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT checked_at FROM check_results ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if row and row["checked_at"]:
        return jsonify({"time": row["checked_at"]})
    return jsonify({"time": None})


@app.route("/api/wg-status", methods=["GET"])
@login_required
def wg_status():
    """检测 WireGuard 接口状态和流量"""
    agent_url = os.environ.get("EYES_AGENT_URL") or get_setting("agent_url", "")
    return jsonify(collect_wireguard_with_agent(agent_url))


@app.route("/api/test-email", methods=["POST"])
@login_required
def test_email():
    """测试邮件推送"""
    settings = get_all_settings()
    
    from_addr = settings.get("email_from", "")
    to_addrs = [addr.strip() for addr in settings.get("email_to", "").split(",") if addr.strip()]
    smtp_host = settings.get("smtp_host", "")
    smtp_port = settings.get("smtp_port", "25")
    smtp_user = settings.get("smtp_user", "")
    smtp_password = settings.get("smtp_password", "")
    use_ssl = settings.get("smtp_ssl") == "1"
    
    if not all([from_addr, to_addrs, smtp_host, smtp_user, smtp_password]):
        return jsonify({"success": False, "error": "邮件配置不完整"})
    
    result = send_test_email(
        from_addr=from_addr,
        to_addrs=to_addrs,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        use_ssl=use_ssl
    )
    return jsonify({"success": result})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
