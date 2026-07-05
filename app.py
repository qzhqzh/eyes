#!/usr/bin/env python3
"""eyes — Flask Web 应用"""

import os
import functools
import subprocess
import re
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from apscheduler.schedulers.background import BackgroundScheduler
from models import (
    init_db, init_default_settings, get_setting, set_setting, get_all_settings,
    get_check_items, get_all_check_items, add_check_item, update_check_item, delete_check_item,
    update_item_status, save_check_result, get_check_results, clear_check_results, import_from_yaml,
    save_resource_metrics, get_resource_metrics, clear_old_metrics
)
from checker import run_check, run_all_checks
from bark import send_bark_alert, send_bark_recovery
from email_sender import send_email_alert, send_email_report, send_test_email
from scanner import scan_all

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.secret_key = "eyes-secret-key-2026-stable"

# 初始化数据库
init_db()
init_default_settings()

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
        r = subprocess.run(
            ["df", "-h", "/mnt/nas"],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode == 0:
            lines = r.stdout.strip().split("\n")
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    stats['nas'] = parts[4].replace('%', '')
                    stats['nas_used'] = parts[2]
                    stats['nas_total'] = parts[1]
                else:
                    stats['nas'] = -1
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


# 启动定时任务调度器
scheduler = BackgroundScheduler()
interval = int(get_setting("resource_collect_interval", "300"))
scheduler.add_job(id='collect_resource_metrics', func=collect_stats, trigger='interval', seconds=interval, replace_existing=True)
scheduler.add_job(id='clear_old_metrics', func=clear_old_metrics, trigger='interval', hours=24)
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
        stored_password = get_setting("web_password", "eyes123")
        if password == stored_password:
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


@app.route("/api/settings", methods=["GET"])
@login_required
def get_settings():
    """获取所有设置"""
    return jsonify(get_all_settings())


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
    items = get_check_items()
    enabled_items = [i for i in items if i["enabled"]]
    
    # 运行检查
    results = run_all_checks(enabled_items)
    
    # 保存结果
    clear_check_results()
    failures = []
    for r in results:
        save_check_result(r["id"], r["type"], r["name"], r["ok"], r["detail"])
        if not r["ok"]:
            failures.append({"name": r["name"], "detail": r["detail"]})
    
    # 发送通知
    settings = get_all_settings()
    
    # Bark 推送
    if settings.get("bark_enabled") == "1" and failures:
        send_bark_alert(
            failures,
            server=settings.get("bark_server", "https://api.day.app"),
            key=settings.get("bark_key", ""),
            group=settings.get("bark_group", "Dev")
        )
    
    # 邮件推送（后续实现）
    # if settings.get("email_enabled") == "1" and failures:
    #     send_email_alert(...)
    
    return jsonify({
        "success": True,
        "total": len(results),
        "passed": sum(1 for r in results if r["ok"]),
        "failed": len(failures),
        "failures": failures
    })


@app.route("/api/results", methods=["GET"])
@login_required
def list_results():
    """获取检查结果"""
    return jsonify(get_check_results())


@app.route("/api/scan", methods=["POST"])
@login_required
def scan_services():
    """扫描系统中的服务"""
    settings = get_all_settings()
    agent_url = settings.get("agent_url", "")
    
    results = scan_all(agent_url if agent_url else None)
    
    # 获取现有监控项
    existing_items = get_check_items()
    existing_targets = {item["target"] for item in existing_items}
    
    # 统计新增
    added_count = 0
    for item_type, items in results.items():
        for item in items:
            if item["target"] not in existing_targets:
                add_check_item(item["type"], item["name"], item["target"])
                added_count += 1
                existing_targets.add(item["target"])
    
    return jsonify({
        "success": True,
        "added": added_count,
        "details": {
            "docker": len(results.get("docker", [])),
            "systemd": len(results.get("systemd", [])),
            "crond": len(results.get("crond", []))
        }
    })


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


@app.route("/api/system-stats", methods=["GET"])
@login_required
def system_stats():
    """获取系统资源统计（实时）"""
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

