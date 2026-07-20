#!/usr/bin/env python3
"""eyes — 定时检查脚本

用于 cron 定时执行检查并发送通知。
用法：
    python cron_check.py          # 执行检查并发送通知
    python cron_check.py --alert  # 只在有异常时发送
    python cron_check.py --report # 始终发送报告
"""

import sys
import os
import argparse

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import get_all_settings, get_check_items, save_check_result, clear_check_results
from checker import run_all_checks
from bark import send_bark_alert


def main():
    parser = argparse.ArgumentParser(description="eyes 定时检查")
    parser.add_argument("--alert", action="store_true", help="只在有异常时发送")
    parser.add_argument("--report", action="store_true", help="始终发送报告")
    args = parser.parse_args()

    # 获取配置
    settings = get_all_settings()
    
    # 获取启用的监控项
    items = get_check_items()
    enabled_items = [i for i in items if i["enabled"]]
    
    if not enabled_items:
        print("没有启用的监控项")
        return
    
    # 运行检查
    print(f"开始检查 {len(enabled_items)} 个监控项...")
    results = run_all_checks(enabled_items)
    
    # 保存结果
    clear_check_results()
    failures = []
    for r in results:
        save_check_result(r["id"], r["type"], r["name"], r["ok"], r["detail"])
        status = "✓" if r["ok"] else "✗"
        print(f"  {status} {r['name']}: {r['detail']}")
        if not r["ok"]:
            failures.append({"name": r["name"], "detail": r["detail"]})
    
    # 统计
    total = len(results)
    passed = sum(1 for r in results if r["ok"])
    failed = total - passed
    print(f"\n检查完成: {passed}/{total} 通过, {failed} 失败")
    
    # 发送通知
    should_notify = False
    if args.report:
        should_notify = True
    elif args.alert and failures:
        should_notify = True
    
    if should_notify:
        # Bark 推送
        if settings.get("bark_enabled") == "1":
            if failures:
                print("发送 Bark 告警...")
                send_bark_alert(
                    failures,
                    server=settings.get("bark_server", "https://api.day.app"),
                    key=settings.get("bark_key", ""),
                    group=settings.get("bark_group", "Dev")
                )
            elif args.report:
                # 报告模式，全部正常时也推送
                from bark import send_bark
                print("发送 Bark 报告...")
                send_bark(
                    title=f"✅ eyes: {passed}/{total} 正常",
                    body="所有服务运行正常",
                    server=settings.get("bark_server", "https://api.day.app"),
                    key=settings.get("bark_key", ""),
                    group=settings.get("bark_group", "Dev")
                )
        
        # 邮件推送（后续实现）
        # if settings.get("email_enabled") == "1":
        #     ...
    
    # 返回退出码
    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
