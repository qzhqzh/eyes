#!/usr/bin/env python3
"""eyes — Bark 推送模块"""

import urllib.request
import urllib.parse
import json


def send_bark(title, body, server="https://api.day.app", key="", group="Dev", sound=None):
    """发送 Bark 推送
    
    Args:
        title: 推送标题
        body: 推送内容
        server: Bark 服务器地址
        key: Device Key
        group: 推送分组
        sound: 推送铃声（可选）
    
    Returns:
        bool: 是否成功
    """
    if not key:
        print("Bark key 未配置")
        return False

    # 构建 URL
    url = f"{server}/{key}"
    
    # 构建 POST 数据
    data = {
        "title": title,
        "body": body,
        "group": group,
    }
    if sound:
        data["sound"] = sound

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("code") == 200
    except Exception as e:
        print(f"Bark 推送失败: {e}")
        return False


def send_bark_alert(failures, server="https://api.day.app", key="", group="Dev"):
    """发送告警推送
    
    Args:
        failures: 失败项列表 [{"name": ..., "detail": ...}]
        server: Bark 服务器地址
        key: Device Key
        group: 推送分组
    """
    if not failures:
        return True

    count = len(failures)
    title = f"⚠ eyes: {count}项异常"
    
    # 简短内容，最多显示3个
    items = failures[:3]
    body = "\n".join(f"• {f['name']}: {f['detail']}" for f in items)
    if count > 3:
        body += f"\n... 还有{count - 3}项"

    return send_bark(title, body, server, key, group)


def send_bark_recovery(recovered_names, server="https://api.day.app", key="", group="Dev"):
    """发送恢复推送"""
    if not recovered_names:
        return True

    count = len(recovered_names)
    title = f"✅ eyes: {count}项恢复"
    body = ", ".join(recovered_names[:5])
    if count > 5:
        body += f" 等{count}项"

    return send_bark(title, body, server, key, group)
