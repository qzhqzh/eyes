#!/usr/bin/env python3
"""eyes — 数据库模型和配置管理"""

import sqlite3
import os
import time
from pathlib import Path

DB_PATH = os.environ.get(
    "EYES_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "eyes.db"),
)


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()

    # 通知配置表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 监控项表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS check_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,  -- docker, systemd, http, port, command, crond
            name TEXT NOT NULL,
            target TEXT NOT NULL,  -- 容器名/unit名/URL/端口号/命令
            enabled INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',  -- active, deprecated
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 迁移：如果表已存在但缺少 status 字段，则添加
    cursor.execute("PRAGMA table_info(check_items)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'status' not in columns:
        cursor.execute("ALTER TABLE check_items ADD COLUMN status TEXT DEFAULT 'active'")

    # 检查结果表（只保留最近一次）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS check_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            item_type TEXT NOT NULL,
            item_name TEXT NOT NULL,
            ok INTEGER NOT NULL,
            detail TEXT,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES check_items(id)
        )
    """)

    # 资源指标历史表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resource_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cpu REAL,
            memory REAL,
            disk REAL,
            nas REAL,
            memory_used TEXT,
            memory_total TEXT,
            disk_used TEXT,
            disk_total TEXT,
            nas_used TEXT,
            nas_total TEXT
        )
    """)

    conn.commit()
    conn.close()


def get_setting(key, default=None):
    """获取配置项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    """设置配置项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO settings (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
    """, (key, value, value))
    conn.commit()
    conn.close()


def claim_operation_cooldown(key, cooldown_seconds, now=None):
    """Atomically claim a cross-process operation cooldown window."""
    timestamp = float(time.time() if now is None else now)
    cooldown_seconds = max(1, int(cooldown_seconds))
    setting_key = f"internal.cooldown.{key}"
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT value FROM settings WHERE key = ?", (setting_key,))
        row = cursor.fetchone()
        try:
            previous = float(row["value"]) if row else 0.0
        except (TypeError, ValueError):
            previous = 0.0
        remaining = cooldown_seconds - (timestamp - previous)
        if remaining > 0:
            conn.commit()
            return False, max(1, int(remaining + 0.999))
        cursor.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (setting_key, str(timestamp)),
        )
        conn.commit()
        return True, 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_all_settings():
    """获取所有配置"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def get_check_items(item_type=None):
    """获取监控项列表（仅 active 状态）"""
    conn = get_db()
    cursor = conn.cursor()
    if item_type:
        cursor.execute("SELECT * FROM check_items WHERE type = ? AND status = 'active' ORDER BY id", (item_type,))
    else:
        cursor.execute("SELECT * FROM check_items WHERE status = 'active' ORDER BY type, id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_check_items(item_type=None):
    """获取所有监控项（包括 deprecated）"""
    conn = get_db()
    cursor = conn.cursor()
    if item_type:
        cursor.execute("SELECT * FROM check_items WHERE type = ? ORDER BY id", (item_type,))
    else:
        cursor.execute("SELECT * FROM check_items ORDER BY type, id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def add_check_item(item_type, name, target):
    """添加监控项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO check_items (type, name, target) VALUES (?, ?, ?)",
        (item_type, name, target)
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    return item_id


def update_item_status(item_id, status):
    """更新监控项状态（active/deprecated）"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE check_items SET status = ? WHERE id = ?",
        (status, item_id)
    )
    conn.commit()
    conn.close()


def update_check_item(item_id, name=None, target=None, enabled=None):
    """更新监控项"""
    conn = get_db()
    cursor = conn.cursor()
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if target is not None:
        updates.append("target = ?")
        params.append(target)
    if enabled is not None:
        updates.append("enabled = ?")
        params.append(1 if enabled else 0)
    if updates:
        params.append(item_id)
        cursor.execute(f"UPDATE check_items SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()


def delete_check_item(item_id):
    """删除监控项"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM check_results WHERE item_id = ?", (item_id,))
    cursor.execute("DELETE FROM check_items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()


def save_check_result(item_id, item_type, item_name, ok, detail):
    """保存检查结果"""
    conn = get_db()
    cursor = conn.cursor()
    # 删除该监控项的旧结果
    cursor.execute("DELETE FROM check_results WHERE item_id = ?", (item_id,))
    # 插入新结果
    cursor.execute("""
        INSERT INTO check_results (item_id, item_type, item_name, ok, detail)
        VALUES (?, ?, ?, ?, ?)
    """, (item_id, item_type, item_name, 1 if ok else 0, detail))
    conn.commit()
    conn.close()


def replace_check_results(results):
    """Atomically replace the complete latest health-check result set."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("DELETE FROM check_results")
        cursor.executemany(
            """
            INSERT INTO check_results (item_id, item_type, item_name, ok, detail)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    result["id"],
                    result["type"],
                    result["name"],
                    1 if result["ok"] else 0,
                    result["detail"],
                )
                for result in results
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_check_results():
    """获取所有检查结果"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.*, i.enabled
        FROM check_results r
        LEFT JOIN check_items i ON r.item_id = i.id
        ORDER BY r.item_type, r.item_name
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def clear_check_results():
    """清空检查结果"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM check_results")
    conn.commit()
    conn.close()


def import_from_yaml(conf_dir):
    """从 YAML 配置文件导入监控项"""
    import yaml
    conf_path = Path(conf_dir)
    if not conf_path.is_dir():
        return

    type_mapping = {
        "docker": "docker",
        "_nginx_docker": "docker",
        "systemd": "systemd",
        "http": "http",
        "port": "port",
        "command": "command",
        "crond": "crond",
        "portscan": "portscan",
    }

    for f in sorted(conf_path.glob("*.yaml")):
        category = f.stem
        item_type = type_mapping.get(category)
        if not item_type:
            continue

        try:
            with open(f) as fh:
                items = yaml.safe_load(fh)
            if not items:
                continue

            for item in items:
                name = item.get("name", "")
                if item_type == "http":
                    target = item.get("url", "")
                elif item_type == "command":
                    target = item.get("command", "")
                else:
                    target = item.get("target", "")

                if name and target:
                    # 检查是否已存在
                    existing = get_check_items(item_type)
                    exists = any(e["name"] == name and e["target"] == str(target) for e in existing)
                    if not exists:
                        add_check_item(item_type, name, str(target))
        except Exception as e:
            print(f"导入 {f.name} 失败: {e}")


def init_default_settings():
    """初始化默认配置"""
    defaults = {
        "bark_enabled": "0",
        "bark_key": "",
        "bark_server": "https://api.day.app",
        "bark_group": "Dev",
        "email_enabled": "0",
        "email_from": "",
        "email_to": "",
        "smtp_host": "",
        "smtp_port": "25",
        "smtp_ssl": "0",
        "smtp_user": "",
        "smtp_password": "",
        "web_password": "",
        "check_interval": "600",  # 秒，10分钟
        "agent_url": "http://host.docker.internal:9091",  # 宿主机 agent 地址
        "resource_collect_interval": "300",  # 秒，5分钟
    }
    for key, value in defaults.items():
        if get_setting(key) is None:
            set_setting(key, value)


def save_resource_metrics(cpu, memory, disk, nas, memory_used, memory_total, disk_used, disk_total, nas_used, nas_total):
    """保存资源指标"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO resource_metrics (cpu, memory, disk, nas, memory_used, memory_total, disk_used, disk_total, nas_used, nas_total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cpu, memory, disk, nas, memory_used, memory_total, disk_used, disk_total, nas_used, nas_total)
    )
    conn.commit()
    conn.close()


def get_resource_metrics(hours=24):
    """获取最近 N 小时的资源指标"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM resource_metrics WHERE timestamp >= datetime('now', '-{}' || ' hours') ORDER BY timestamp".format(hours)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def clear_old_metrics(days=7):
    """清理 N 天前的旧数据"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM resource_metrics WHERE timestamp < date('now', '-{}' || ' days')".format(days)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    init_default_settings()
    print("数据库初始化完成")
