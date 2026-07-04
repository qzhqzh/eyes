#!/usr/bin/env python3
"""eyes — 邮件推送模块"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def send_email_alert(failures, from_addr, to_addrs, smtp_host, smtp_port, 
                     smtp_user, smtp_password, use_ssl=False):
    """发送告警邮件
    
    Args:
        failures: [{"name": ..., "detail": ...}]
        from_addr: 发件人
        to_addrs: 收件人列表
        smtp_host: SMTP 服务器
        smtp_port: SMTP 端口
        smtp_user: SMTP 用户名
        smtp_password: SMTP 密码
        use_ssl: 是否使用 SSL
    """
    if not failures:
        return True

    count = len(failures)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建邮件
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠ eyes: {count}项异常 [{now_str}]"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    
    # 纯文本
    text_lines = [f"⚠ 服务异常告警", f"时间: {now_str}", ""]
    for f in failures:
        text_lines.append(f"✗ {f['name']}: {f['detail']}")
    text_body = "\n".join(text_lines)
    
    # HTML
    html_rows = ""
    for f in failures:
        html_rows += f'<tr><td style="padding:8px;border:1px solid #ddd">❌</td><td style="padding:8px;border:1px solid #ddd">{f["name"]}</td><td style="padding:8px;border:1px solid #ddd;color:#e74c3c">{f["detail"]}</td></tr>'
    
    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#e74c3c;color:#fff;padding:16px;border-radius:8px 8px 0 0;text-align:center">
  <h2 style="margin:0">⚠ 服务异常告警</h2>
  <p style="margin:8px 0 0 0;opacity:0.9">{now_str}</p>
</div>
<div style="border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;padding:16px">
  <p><strong>{count} 项服务异常：</strong></p>
  <table style="width:100%;border-collapse:collapse">
    <tr style="background:#f8f9fa"><th style="padding:8px;border:1px solid #ddd">状态</th><th style="padding:8px;border:1px solid #ddd">服务</th><th style="padding:8px;border:1px solid #ddd">详情</th></tr>
    {html_rows}
  </table>
</div>
<div style="text-align:center;padding:16px;color:#999;font-size:12px">eyes — 服务健康监控</div>
</body></html>"""
    
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    # 发送
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=30)
            server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False


def send_email_report(total, passed, failures, from_addr, to_addrs, smtp_host, 
                      smtp_port, smtp_user, smtp_password, use_ssl=False):
    """发送报告邮件"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    failed = total - passed
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 eyes: {passed}/{total} 正常 [{now_str}]"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    
    # 纯文本
    text_lines = [
        "📊 每日服务健康报告",
        f"时间: {now_str}",
        f"总数: {total}  通过: {passed}  失败: {failed}",
        ""
    ]
    if failures:
        text_lines.append("异常项:")
        for f in failures:
            text_lines.append(f"  ✗ {f['name']}: {f['detail']}")
    else:
        text_lines.append("✓ 全部正常")
    text_body = "\n".join(text_lines)
    
    # HTML
    status_color = "#28a745" if failed == 0 else "#e74c3c"
    status_text = "✓ 全部正常" if failed == 0 else f"✗ {failed} 项异常"
    
    fail_rows = ""
    if failures:
        for f in failures:
            fail_rows += f'<tr><td style="padding:8px;border:1px solid #ddd">❌</td><td style="padding:8px;border:1px solid #ddd">{f["name"]}</td><td style="padding:8px;border:1px solid #ddd;color:#e74c3c">{f["detail"]}</td></tr>'
    
    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:{status_color};color:#fff;padding:16px;border-radius:8px 8px 0 0;text-align:center">
  <h2 style="margin:0">📊 每日服务健康报告</h2>
  <p style="margin:8px 0 0 0;opacity:0.9">{now_str}</p>
</div>
<div style="border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;padding:16px">
  <div style="text-align:center;font-size:18px;margin-bottom:16px">
    <span style="color:#28a745;font-weight:bold">{passed}</span> / {total}
    <span style="color:{status_color};margin-left:12px">{status_text}</span>
  </div>
  {"<table style='width:100%;border-collapse:collapse'><tr style='background:#f8f9fa'><th style='padding:8px;border:1px solid #ddd'>状态</th><th style='padding:8px;border:1px solid #ddd'>服务</th><th style='padding:8px;border:1px solid #ddd'>详情</th></tr>" + fail_rows + "</table>" if failures else ""}
</div>
<div style="text-align:center;padding:16px;color:#999;font-size:12px">eyes — 服务健康监控</div>
</body></html>"""
    
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=30)
            server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False


def send_test_email(from_addr, to_addrs, smtp_host, smtp_port, 
                    smtp_user, smtp_password, use_ssl=False):
    """发送测试邮件"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"✅ eyes 测试邮件 [{now_str}]"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    
    text_body = f"✅ eyes 测试邮件\n\n时间: {now_str}\n\n这是一封测试邮件，证明邮件配置正确。"
    
    html_body = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:sans-serif;max-width:600px;margin:0 auto;padding:20px">
<div style="background:#28a745;color:#fff;padding:16px;border-radius:8px 8px 0 0;text-align:center">
  <h2 style="margin:0">✅ eyes 测试邮件</h2>
  <p style="margin:8px 0 0 0;opacity:0.9">{now_str}</p>
</div>
<div style="border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px;padding:16px;text-align:center">
  <p style="font-size:16px">这是一封测试邮件</p>
  <p style="color:#666">证明邮件配置正确 ✓</p>
</div>
<div style="text-align:center;padding:16px;color:#999;font-size:12px">eyes — 服务健康监控</div>
</body></html>"""
    
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=30)
            server.ehlo()
        server.login(smtp_user, smtp_password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"邮件发送失败: {e}")
        return False
