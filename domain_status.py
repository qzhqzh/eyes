#!/usr/bin/env python3
"""Discover proxied domains from nginx config and probe their HTTP status."""

import glob
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone


SERVER_NAME_RE = re.compile(r"\bserver_name\s+([^;]+);")
PROXY_PASS_RE = re.compile(r"\bproxy_pass\s+([^;]+);")
DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$", re.I)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Keep probes on the configured host; a redirect itself proves HTTP reachability."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def nginx_server_blocks(content):
    """Extract server blocks while respecting nested location braces."""
    blocks = []
    for match in re.finditer(r"\bserver\s*\{", content):
        depth = 1
        cursor = match.end()
        while cursor < len(content) and depth:
            if content[cursor] == "{":
                depth += 1
            elif content[cursor] == "}":
                depth -= 1
            cursor += 1
        if depth == 0:
            blocks.append(content[match.end():cursor - 1])
    return blocks


def discover_domains(config_dir):
    """Return unique domains and upstreams declared in nginx config files."""
    domains = {}
    for path in sorted(glob.glob(os.path.join(config_dir, "*.conf"))):
        try:
            with open(path, encoding="utf-8") as handle:
                content = re.sub(r"#.*", "", handle.read())
        except OSError:
            continue
        for block in nginx_server_blocks(content):
            upstreams = sorted(set(PROXY_PASS_RE.findall(block)))
            for declaration in SERVER_NAME_RE.findall(block):
                for domain in declaration.split():
                    domain = domain.strip().lower()
                    if not DOMAIN_RE.fullmatch(domain):
                        continue
                    entry = domains.setdefault(
                        domain, {"domain": domain, "upstreams": set(), "sources": set()}
                    )
                    entry["upstreams"].update(upstreams)
                    entry["sources"].add(os.path.basename(path))
    return [
        {
            "domain": entry["domain"],
            "upstreams": sorted(entry["upstreams"]),
            "sources": sorted(entry["sources"]),
        }
        for entry in sorted(domains.values(), key=lambda item: item["domain"])
    ]


def probe_domain(domain, timeout=5):
    """Probe HTTPS and distinguish 404 from network-level failure."""
    started = time.monotonic()
    request = urllib.request.Request(
        f"https://{domain}/",
        headers={"User-Agent": "eyes-domain-monitor/1.0", "Range": "bytes=0-0"},
    )
    try:
        opener = urllib.request.build_opener(NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            status_code = response.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "domain": domain,
            "state": "unreachable",
            "reachable": False,
            "status_code": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
            "detail": str(getattr(exc, "reason", exc)),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    state = "not_found" if status_code == 404 else (
        "healthy" if 200 <= status_code < 400 else "http_error"
    )
    return {
        "domain": domain,
        "state": state,
        "reachable": True,
        "status_code": status_code,
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "detail": f"HTTP {status_code}",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_domain_status(config_dir, only_domain=None, workers=8):
    """Discover domains and probe all or one configured domain concurrently."""
    entries = discover_domains(config_dir)
    if only_domain:
        entries = [entry for entry in entries if entry["domain"] == only_domain.lower()]
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(entries) or 1))) as executor:
        statuses = list(executor.map(lambda entry: probe_domain(entry["domain"]), entries))
    by_domain = {status["domain"]: status for status in statuses}
    return [{**entry, **by_domain[entry["domain"]]} for entry in entries]
