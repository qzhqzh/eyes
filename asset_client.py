#!/usr/bin/env python3
"""Sanitized client for the loopback Eyes asset probe."""

import json
import urllib.error
import urllib.parse
import urllib.request


class AssetProbeError(RuntimeError):
    pass


def _request(base_url, path, query=None, payload=None, timeout=45):
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method="POST" if data else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("error")
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = None
        raise AssetProbeError(detail or f"asset probe returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AssetProbeError("asset probe is unavailable") from exc


def fetch_model_assets(base_url, refresh=False):
    return _request(
        base_url, "/api/models", {"refresh": "1" if refresh else "0"}
    ).get("models", [])


def fetch_context7_accounts(base_url, refresh=False):
    return _request(
        base_url,
        "/api/context7/accounts",
        {"refresh": "1" if refresh else "0"},
    ).get("accounts", [])


def call_context7_pool(base_url, path, params):
    return _request(
        base_url,
        "/api/context7/request",
        payload={"path": path, "params": params},
    )
