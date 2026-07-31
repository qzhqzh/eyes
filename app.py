#!/usr/bin/env python3
"""eyes — Flask Web 应用"""

import os
import functools
import fcntl
import hmac
import json
import secrets
import subprocess
import re
import threading
import time
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
from domain_status import collect_domain_status
from asset_client import (
    AssetProbeError,
    call_context7_pool,
    fetch_context7_accounts,
    fetch_model_assets,
)


def _secret_value(env_name, file_env_name, max_bytes=4096):
    direct = os.environ.get(env_name, "").strip()
    if direct:
        return direct
    file_path = os.environ.get(file_env_name, "").strip()
    if not file_path:
        return ""
    try:
        with open(file_path, encoding="utf-8") as handle:
            value = handle.read(max_bytes + 1).strip()
    except (OSError, UnicodeError):
        return ""
    return value if len(value.encode("utf-8")) <= max_bytes else ""


app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
secure_config_required = os.environ.get("EYES_REQUIRE_SECURE_CONFIG") == "1"
configured_secret = os.environ.get("EYES_SECRET_KEY", "")
configured_web_password = os.environ.get("EYES_WEB_PASSWORD", "")
configured_enroll_token = os.environ.get("EYES_HUB_ENROLL_TOKEN", "")
configured_asset_api_token = _secret_value(
    "EYES_ASSET_API_TOKEN", "EYES_ASSET_API_TOKEN_FILE"
)
secure_values = (configured_secret, configured_web_password, configured_enroll_token)
if secure_config_required and (
    not configured_secret
    or not configured_web_password
    or len(configured_secret) < 32
    or len(configured_web_password) < 12
    or (configured_enroll_token and len(configured_enroll_token) < 24)
    or (configured_asset_api_token and len(configured_asset_api_token) < 24)
    or any(value.lower().startswith("replace-with-") for value in secure_values)
    or configured_asset_api_token.lower().startswith("replace-with-")
):
    raise RuntimeError(
        "set non-placeholder EYES_SECRET_KEY (32+ chars), EYES_WEB_PASSWORD "
        "(12+ chars), and optional EYES_HUB_ENROLL_TOKEN/EYES_ASSET_API_TOKEN "
        "or EYES_ASSET_API_TOKEN_FILE (24+ chars)"
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
GATEWAY_CONFIG_DIR = os.environ.get("EYES_GATEWAY_CONFIG_DIR", "/gateway/nginx/conf.d")
ASSET_PROBE_URL = os.environ.get("EYES_ASSET_PROBE_URL", "http://127.0.0.1:9092")
SUPPORTED_MCP_PROTOCOL_VERSION = "2025-03-26"


def _bounded_env_int(name, default, minimum, maximum):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


ASSET_MCP_RATE_LIMIT_PER_MINUTE = _bounded_env_int(
    "EYES_ASSET_MCP_RATE_LIMIT_PER_MINUTE", 30, 1, 600
)
ASSET_MCP_MAX_REQUEST_BYTES = _bounded_env_int(
    "EYES_ASSET_MCP_MAX_REQUEST_BYTES", 32768, 1024, 1024 * 1024
)
ASSET_MCP_MAX_QUERY_CHARS = _bounded_env_int(
    "EYES_ASSET_MCP_MAX_QUERY_CHARS", 2000, 64, 8000
)
ASSET_MCP_ALLOWED_ORIGINS = {
    item.strip()
    for item in os.environ.get("EYES_ASSET_MCP_ALLOWED_ORIGINS", "").split(",")
    if item.strip()
}
ASSET_MCP_RATE_CLEANUP_INTERVAL_SECONDS = 60
_asset_mcp_request_times = {}
_asset_mcp_rate_lock = threading.Lock()
_asset_mcp_last_cleanup = 0.0


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
DASHBOARD_REFRESH_DEFAULT_INTERVALS = {
    "wireguard": 60,
    "network_speed": 600,
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


@app.route("/domains")
@login_required
def domains():
    """Proxy domain inventory and reachability dashboard."""
    return render_template("domains.html", active_page="domains")


@app.route("/api/domains", methods=["GET"])
@login_required
def domain_inventory():
    """Return configured proxy domains with live reachability status."""
    return jsonify(collect_domain_status(GATEWAY_CONFIG_DIR))


@app.route("/api/domains/<domain>/status", methods=["GET"])
@login_required
def domain_status(domain):
    """Refresh one configured domain without allowing arbitrary probes."""
    results = collect_domain_status(GATEWAY_CONFIG_DIR, only_domain=domain)
    if not results:
        return jsonify({"error": "domain is not configured"}), 404
    return jsonify(results[0])


@app.route("/assets")
@login_required
def assets():
    """Model and Context7 asset aggregation dashboard."""
    return render_template(
        "assets.html",
        active_page="assets",
        asset_mcp_enabled=bool(configured_asset_api_token),
    )


@app.route("/api/assets/models", methods=["GET"])
@login_required
def asset_models():
    try:
        return jsonify({
            "models": fetch_model_assets(
                ASSET_PROBE_URL, refresh=request.args.get("refresh") == "1"
            )
        })
    except AssetProbeError as exc:
        return jsonify({"error": str(exc)}), 503


@app.route("/api/assets/context7", methods=["GET"])
@login_required
def asset_context7():
    try:
        return jsonify({
            "accounts": fetch_context7_accounts(
                ASSET_PROBE_URL, refresh=request.args.get("refresh") == "1"
            ),
            "mcp_enabled": bool(configured_asset_api_token),
        })
    except AssetProbeError as exc:
        return jsonify({"error": str(exc)}), 503


def _mcp_error(request_id, code, message):
    return jsonify({
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    })


def _asset_mcp_rate_allowed(client_key):
    global _asset_mcp_last_cleanup
    now = time.monotonic()
    with _asset_mcp_rate_lock:
        if (
            now - _asset_mcp_last_cleanup
            >= ASSET_MCP_RATE_CLEANUP_INTERVAL_SECONDS
        ):
            for key, seen_times in list(_asset_mcp_request_times.items()):
                active_times = [
                    seen_at for seen_at in seen_times if now - seen_at < 60
                ]
                if active_times:
                    _asset_mcp_request_times[key] = active_times
                else:
                    _asset_mcp_request_times.pop(key, None)
            _asset_mcp_last_cleanup = now

        recent = [
            seen_at
            for seen_at in _asset_mcp_request_times.get(client_key, [])
            if now - seen_at < 60
        ]
        if len(recent) >= ASSET_MCP_RATE_LIMIT_PER_MINUTE:
            _asset_mcp_request_times[client_key] = recent
            return False
        recent.append(now)
        _asset_mcp_request_times[client_key] = recent
        return True


def _context7_mcp_tools():
    return [
        {
            "name": "resolve-library-id",
            "title": "Resolve Context7 Library ID",
            "description": "Search Context7 for the library ID that best matches a package or product.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "libraryName": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["libraryName", "query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "query-docs",
            "title": "Query Context7 Documentation",
            "description": "Retrieve current documentation snippets for an exact Context7 library ID.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "libraryId": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["libraryId", "query"],
                "additionalProperties": False,
            },
        },
    ]


@app.route("/mcp/context7", methods=["POST"])
def context7_mcp():
    """Stateless MCP facade backed by the local multi-account Context7 pool."""
    if not configured_asset_api_token:
        return _mcp_error(None, -32001, "asset MCP is not configured"), 503
    authorization = request.headers.get("Authorization", "")
    expected = f"Bearer {configured_asset_api_token}"
    if not hmac.compare_digest(authorization, expected):
        return _mcp_error(None, -32001, "MCP authorization failed"), 401

    origin = request.headers.get("Origin")
    if origin and origin not in ASSET_MCP_ALLOWED_ORIGINS:
        return _mcp_error(None, -32001, "MCP origin is not allowed"), 403
    if request.content_length is not None and (
        request.content_length <= 0
        or request.content_length > ASSET_MCP_MAX_REQUEST_BYTES
    ):
        return _mcp_error(None, -32600, "invalid MCP request size"), 413
    client_key = request.remote_addr or "unknown"
    if not _asset_mcp_rate_allowed(client_key):
        response = _mcp_error(None, -32003, "MCP request rate limit exceeded")
        response.headers["Retry-After"] = "60"
        return response, 429

    raw_payload = request.stream.read(ASSET_MCP_MAX_REQUEST_BYTES + 1)
    if not raw_payload or len(raw_payload) > ASSET_MCP_MAX_REQUEST_BYTES:
        return _mcp_error(None, -32600, "invalid MCP request size"), 413
    try:
        payload = json.loads(raw_payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
        return _mcp_error(None, -32600, "invalid JSON-RPC request"), 400
    request_id = payload.get("id")
    method = payload.get("method")
    protocol_version = request.headers.get("MCP-Protocol-Version")
    if (
        method != "initialize"
        and protocol_version
        and protocol_version != SUPPORTED_MCP_PROTOCOL_VERSION
    ):
        return _mcp_error(
            request_id, -32600, "unsupported MCP protocol version"
        ), 400
    if method == "notifications/initialized":
        return "", 202
    if method == "initialize":
        return jsonify({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": SUPPORTED_MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "eyes-context7-pool", "version": "0.1.0"},
                "instructions": "Context7 documentation tools use a pooled account quota managed by Eyes.",
            },
        })
    if method == "tools/list":
        return jsonify({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": _context7_mcp_tools()},
        })
    if method != "tools/call":
        return _mcp_error(request_id, -32601, "method not found")

    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return _mcp_error(request_id, -32602, "invalid tool parameters")
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, dict):
        return _mcp_error(request_id, -32602, "invalid tool arguments")
    if tool_name == "resolve-library-id":
        path = "/api/v2/libs/search"
        api_params = {
            "libraryName": arguments.get("libraryName", ""),
            "query": arguments.get("query", ""),
        }
    elif tool_name == "query-docs":
        path = "/api/v2/context"
        api_params = {
            "libraryId": arguments.get("libraryId", ""),
            "query": arguments.get("query", ""),
            "type": "json",
        }
    else:
        return _mcp_error(request_id, -32602, "unknown tool")
    required_values = [
        value for key, value in api_params.items() if key != "type"
    ]
    if (
        not all(isinstance(value, str) and value.strip() for value in required_values)
        or any(len(value) > ASSET_MCP_MAX_QUERY_CHARS for value in required_values)
    ):
        return _mcp_error(
            request_id, -32602, "missing or oversized tool arguments"
        )

    try:
        result = call_context7_pool(ASSET_PROBE_URL, path, api_params)
    except AssetProbeError as exc:
        return _mcp_error(request_id, -32002, str(exc)), 503
    body = result.get("body")
    is_error = int(result.get("status_code", 500)) >= 400
    text_body = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
    tool_result = {
        "content": [{"type": "text", "text": text_body}],
        "isError": is_error,
    }
    if isinstance(body, dict):
        tool_result["structuredContent"] = body
    return jsonify({"jsonrpc": "2.0", "id": request_id, "result": tool_result})


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
        data = request.get_json(silent=True) or {}
        group = data.get("group")
        if group not in HEALTH_GROUP_TYPES and group not in DASHBOARD_REFRESH_DEFAULT_INTERVALS:
            return jsonify({"error": "unknown health group"}), 400
        try:
            seconds = int(data.get("minutes")) * 60
        except (TypeError, ValueError):
            return jsonify({"error": "minutes must be an integer"}), 400
        if seconds < 60 or seconds > 86400:
            return jsonify({"error": "interval must be between 1 minute and 24 hours"}), 400
        if group in HEALTH_GROUP_TYPES:
            if os.environ.get("EYES_ENABLE_SCHEDULED_CHECKS") != "1":
                return jsonify({"error": "scheduled health checks are disabled"}), 409
            set_setting(f"check_interval_{group}", str(seconds))
            job = scheduler.get_job(f"collect_health_{group}")
            if job:
                scheduler.reschedule_job(
                    f"collect_health_{group}", trigger="interval", seconds=seconds
                )
        else:
            set_setting(f"dashboard_refresh_interval_{group}", str(seconds))
        return jsonify({"success": True, "group": group, "seconds": seconds})

    intervals = {
        group: int(get_setting(
            f"check_interval_{group}", str(HEALTH_GROUP_DEFAULT_INTERVALS[group])
        ))
        for group in HEALTH_GROUP_TYPES
    }
    intervals["resources"] = int(get_setting("resource_collect_interval", "300"))
    intervals.update({
        group: int(get_setting(
            f"dashboard_refresh_interval_{group}", str(default_seconds)
        ))
        for group, default_seconds in DASHBOARD_REFRESH_DEFAULT_INTERVALS.items()
    })
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
