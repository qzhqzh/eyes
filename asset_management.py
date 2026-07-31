#!/usr/bin/env python3
"""Aggregate model providers and pooled Context7 accounts without exposing keys."""

import configparser
import ipaddress
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yaml

from domain_status import NoRedirectHandler


MODEL_CACHE_SECONDS = 300
CONTEXT7_CACHE_SECONDS = 300
CONTEXT7_REFRESH_COOLDOWN_SECONDS = 30
CONTEXT7_QUERY_CACHE_SECONDS = 21600
CONTEXT7_QUERY_CACHE_MAX_ITEMS = 128
MAX_UPSTREAM_RESPONSE_BYTES = 4 * 1024 * 1024
CONTEXT7_API_BASE = "https://context7.com"
PROVIDER_ALIASES = {"qwen": "dashscope"}
PROVIDER_MODE_ALIASES = {
    "anthropic_compatible": "anthropic_messages",
    "openai_compatible": "chat_completions",
}
ALLOWED_CONTEXT7_PATHS = {"/api/v2/libs/search", "/api/v2/context"}

_model_cache = {"at": 0.0, "items": []}
_context7_cache = {"at": 0.0, "items": []}
_context7_query_cache = {}
_context7_runtime = {}
_context7_cursor = 0
_cache_lock = threading.Lock()
_context7_refresh_lock = threading.Lock()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_env_file(path):
    """Load a simple KEY=VALUE file without exporting values to process state."""
    values = {}
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return values
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _safe_yaml(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}


def _public_url(value):
    """Return a display URL without userinfo, query parameters, or fragments."""
    try:
        parsed = urllib.parse.urlsplit(value)
        if not parsed.scheme or not parsed.hostname:
            return ""
        hostname = parsed.hostname
        if ":" in hostname:
            hostname = f"[{hostname}]"
        port = f":{parsed.port}" if parsed.port else ""
        return urllib.parse.urlunsplit(
            (parsed.scheme, f"{hostname}{port}", parsed.path, "", "")
        )
    except (TypeError, ValueError):
        return ""


def _public_model(asset):
    public = {key: value for key, value in asset.items() if not key.startswith("_")}
    public["base_url"] = _public_url(public.get("base_url", ""))
    return public


def _canonical_provider(provider):
    return PROVIDER_ALIASES.get(provider, provider)


def discover_model_assets(ai_key_dir, totemora_config_dir):
    """Merge ai-key providers and Totemora member models into one catalog."""
    assets = {}
    provider_metadata = {}
    provider_config = os.path.join(ai_key_dir, "providers.conf")
    provider_env = load_env_file(os.path.join(ai_key_dir, ".env"))
    parser = configparser.ConfigParser()
    parser.read(provider_config, encoding="utf-8")

    for provider in parser.sections():
        env_key = parser.get(provider, "env_key", fallback="")
        api_key = provider_env.get(env_key, "")
        provider_metadata[provider] = {
            "provider_name": parser.get(provider, "name", fallback=provider),
            "api_mode": parser.get(
                provider, "api_mode", fallback="openai_compatible"
            ),
            "base_url": parser.get(provider, "base_url", fallback=""),
        }
        models_value = parser.get(provider, "models", fallback="") or parser.get(
            provider, "model", fallback=""
        )
        for model in (item.strip() for item in models_value.split(",")):
            if not model:
                continue
            key = (provider, model)
            assets[key] = {
                "id": f"{provider}:{model}",
                "provider": provider,
                "provider_name": provider_metadata[provider]["provider_name"],
                "model": model,
                "api_mode": provider_metadata[provider]["api_mode"],
                "base_url": provider_metadata[provider]["base_url"],
                "configured": bool(api_key),
                "sources": ["ai-key"],
                "agents": [],
                "_api_key": api_key,
            }

    providers_doc = _safe_yaml(os.path.join(totemora_config_dir, "providers.yaml"))
    agents_doc = _safe_yaml(os.path.join(totemora_config_dir, "agents.yaml"))
    totemora_providers = providers_doc.get("providers", {})
    for agent in agents_doc.get("agents", []):
        provider_id = str(agent.get("provider", ""))
        canonical_provider = _canonical_provider(provider_id)
        model = str(agent.get("model", ""))
        if not canonical_provider or not model:
            continue
        key = (canonical_provider, model)
        provider = totemora_providers.get(provider_id, {})
        env_key = provider.get("api_key_env", "")
        totemora_api_key = os.environ.get(env_key, "") if env_key else ""
        asset = assets.setdefault(
            key,
            {
                "id": f"{canonical_provider}:{model}",
                "provider": canonical_provider,
                "provider_name": provider_id,
                "model": model,
                "api_mode": PROVIDER_MODE_ALIASES.get(
                    provider.get("type", "unknown"),
                    provider.get("type", "unknown"),
                ),
                "base_url": provider.get("base_url", ""),
                "configured": bool(totemora_api_key),
                "sources": [],
                "agents": [],
                "_api_key": totemora_api_key,
            },
        )
        if "totemora" not in asset["sources"]:
            asset["sources"].append("totemora")
        agent_id = str(agent.get("id", ""))
        if agent_id and agent_id not in asset["agents"]:
            asset["agents"].append(agent_id)

    return list(assets.values())


def _valid_external_https_url(value):
    try:
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        if parsed.hostname.lower() == "localhost":
            return False
        try:
            return not ipaddress.ip_address(parsed.hostname).is_private
        except ValueError:
            return True
    except ValueError:
        return False


def probe_model(asset, timeout=15):
    """Perform a one-token provider call and return sanitized health evidence."""
    result = _public_model(asset)
    result.update({"checked_at": _now_iso(), "latency_ms": None})
    api_key = asset.get("_api_key", "")
    if not api_key:
        result.update({"state": "unconfigured", "status_code": None})
        return result
    base_url = asset.get("base_url", "").rstrip("/")
    if not _valid_external_https_url(base_url):
        result.update({"state": "unsafe_config", "status_code": None})
        return result

    mode = asset.get("api_mode")
    if mode == "anthropic_messages":
        url = f"{base_url}/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    elif mode == "openai_responses":
        url = f"{base_url}/responses"
        headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}
    else:
        url = f"{base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "content-type": "application/json"}

    if mode == "openai_responses":
        payload = {"model": asset["model"], "max_output_tokens": 1, "input": "."}
    else:
        payload = {
            "model": asset["model"],
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "."}],
        }
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    started = time.monotonic()
    try:
        opener = urllib.request.build_opener(NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            status_code = response.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        result.update({
            "state": "unreachable",
            "status_code": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 1),
        })
        return result

    state = {
        200: "healthy",
        401: "auth_error",
        402: "quota_exhausted",
        403: "auth_error",
        429: "rate_limited",
    }.get(status_code, "provider_error")
    result.update({
        "state": state,
        "status_code": status_code,
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
    })
    return result


def get_model_assets(ai_key_dir, totemora_config_dir, refresh=False):
    """Return cached model health; explicit refresh performs real provider calls."""
    with _cache_lock:
        fresh = time.monotonic() - _model_cache["at"] < MODEL_CACHE_SECONDS
        if _model_cache["items"] and fresh and not refresh:
            return _model_cache["items"]
    assets = discover_model_assets(ai_key_dir, totemora_config_dir)
    with ThreadPoolExecutor(max_workers=max(1, min(4, len(assets) or 1))) as executor:
        items = list(executor.map(probe_model, assets))
    items.sort(key=lambda item: (item["provider"], item["model"]))
    with _cache_lock:
        _model_cache.update({"at": time.monotonic(), "items": items})
    return items


def load_context7_accounts(raw=None):
    """Parse label=ctx7sk entries from a secret file or environment variable."""
    if raw is None:
        raw = os.environ.get("EYES_CONTEXT7_ACCOUNTS", "")
        accounts_file = os.environ.get("EYES_CONTEXT7_ACCOUNTS_FILE", "")
        if not raw and accounts_file:
            try:
                with open(accounts_file, encoding="utf-8") as handle:
                    raw = handle.read(64 * 1024 + 1)
                if len(raw.encode("utf-8")) > 64 * 1024:
                    raw = ""
            except (OSError, UnicodeError):
                raw = ""
    accounts = []
    seen_keys = set()
    seen_labels = set()
    for index, entry in enumerate(raw.replace("\n", ",").split(","), start=1):
        entry = entry.strip()
        if not entry or entry.startswith("#"):
            continue
        if "=" in entry:
            label, api_key = entry.split("=", 1)
        else:
            label, api_key = f"account-{index}", entry
        label, api_key = label.strip(), api_key.strip()
        if (
            not label
            or not api_key.startswith("ctx7sk")
            or api_key in seen_keys
            or label in seen_labels
        ):
            continue
        seen_keys.add(api_key)
        seen_labels.add(label)
        accounts.append({"label": label, "_api_key": api_key})
    return accounts


def _header_int(headers, name):
    try:
        return int(headers.get(name)) if headers.get(name) is not None else None
    except (TypeError, ValueError):
        return None


def _context7_state(label, status_code, headers, latency_ms):
    state = "healthy"
    if status_code == 429:
        state = "quota_exhausted"
    elif status_code in {401, 403}:
        state = "auth_error"
    elif status_code >= 500:
        state = "service_error"
    return {
        "label": label,
        "state": state,
        "status_code": status_code,
        "limit": _header_int(headers, "RateLimit-Limit"),
        "remaining": _header_int(headers, "RateLimit-Remaining"),
        "reset_at": _header_int(headers, "RateLimit-Reset"),
        "retry_after_seconds": _header_int(headers, "Retry-After"),
        "latency_ms": latency_ms,
        "checked_at": _now_iso(),
    }


def _call_context7(api_key, path, params=None, timeout=15):
    if path not in ALLOWED_CONTEXT7_PATHS:
        raise ValueError("unsupported Context7 endpoint")
    query = urllib.parse.urlencode(params or {})
    url = f"{CONTEXT7_API_BASE}{path}" + (f"?{query}" if query else "")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "eyes-context7-pool/1.0",
        },
    )
    started = time.monotonic()
    try:
        opener = urllib.request.build_opener(NoRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(MAX_UPSTREAM_RESPONSE_BYTES + 1)
            if len(body) > MAX_UPSTREAM_RESPONSE_BYTES:
                raise ValueError("Context7 response exceeds the configured size limit")
            return (
                response.status,
                body,
                response.headers,
                round((time.monotonic() - started) * 1000, 1),
            )
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_UPSTREAM_RESPONSE_BYTES + 1)
        if len(body) > MAX_UPSTREAM_RESPONSE_BYTES:
            raise ValueError("Context7 response exceeds the configured size limit")
        return (
            exc.code,
            body,
            exc.headers,
            round((time.monotonic() - started) * 1000, 1),
        )


def get_context7_accounts(refresh=False):
    """Return quota evidence with cached, single-flight account probing."""
    accounts = load_context7_accounts()
    if not accounts:
        return []

    def cached_items():
        with _cache_lock:
            items = _context7_cache["items"]
            if not items:
                return None
            max_age = (
                CONTEXT7_REFRESH_COOLDOWN_SECONDS
                if refresh
                else CONTEXT7_CACHE_SECONDS
            )
            if time.monotonic() - _context7_cache["at"] < max_age:
                return items
        return None

    cached = cached_items()
    if cached is not None:
        return cached

    def probe(account):
        started = time.monotonic()
        try:
            status, _, headers, latency = _call_context7(
                account["_api_key"],
                "/api/v2/libs/search",
                {"libraryName": "react", "query": "health check"},
            )
            return _context7_state(account["label"], status, headers, latency)
        except (urllib.error.URLError, TimeoutError, OSError):
            return {
                "label": account["label"],
                "state": "unreachable",
                "status_code": None,
                "limit": None,
                "remaining": None,
                "reset_at": None,
                "retry_after_seconds": None,
                "latency_ms": round((time.monotonic() - started) * 1000, 1),
                "checked_at": _now_iso(),
            }

    with _context7_refresh_lock:
        cached = cached_items()
        if cached is not None:
            return cached
        with ThreadPoolExecutor(max_workers=min(4, len(accounts))) as executor:
            items = list(executor.map(probe, accounts))
        with _cache_lock:
            _context7_runtime.update({item["label"]: item for item in items})
            _context7_cache.update({"at": time.monotonic(), "items": items})
        return items


class Context7PoolError(RuntimeError):
    def __init__(self, message, status_code=503):
        super().__init__(message)
        self.status_code = status_code


def pooled_context7_request(path, params=None):
    """Use the next available account and fail over on auth/quota errors."""
    global _context7_cursor
    accounts = load_context7_accounts()
    if not accounts:
        raise Context7PoolError("no Context7 accounts configured")
    query_key = (
        path,
        tuple(sorted((str(key), str(value)) for key, value in (params or {}).items())),
    )
    with _cache_lock:
        cached = _context7_query_cache.get(query_key)
        if cached and time.monotonic() - cached["at"] < CONTEXT7_QUERY_CACHE_SECONDS:
            return cached["result"] | {"cache_hit": True}
        if cached:
            _context7_query_cache.pop(query_key, None)
    with _cache_lock:
        start = _context7_cursor % len(accounts)
        _context7_cursor += 1
    ordered = accounts[start:] + accounts[:start]
    last_status = 503
    for account in ordered:
        runtime = _context7_runtime.get(account["label"], {})
        reset_at = runtime.get("reset_at")
        quota_still_exhausted = (
            runtime.get("state") == "quota_exhausted"
            and (not reset_at or reset_at > int(time.time()))
        )
        if runtime.get("state") == "auth_error" or quota_still_exhausted:
            continue
        try:
            status, body, headers, latency = _call_context7(
                account["_api_key"], path, params
            )
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
        state = _context7_state(account["label"], status, headers, latency)
        with _cache_lock:
            _context7_runtime[account["label"]] = state
            _context7_cache["items"] = [
                state if item["label"] == account["label"] else item
                for item in _context7_cache["items"]
            ]
        last_status = status
        if status not in {401, 403, 429}:
            result = {
                "status_code": status,
                "body": body,
                "content_type": headers.get("Content-Type", "application/json"),
                "account_label": account["label"],
                "cache_hit": False,
            }
            if status == 200:
                with _cache_lock:
                    if len(_context7_query_cache) >= CONTEXT7_QUERY_CACHE_MAX_ITEMS:
                        oldest_key = min(
                            _context7_query_cache,
                            key=lambda key: _context7_query_cache[key]["at"],
                        )
                        _context7_query_cache.pop(oldest_key, None)
                    _context7_query_cache[query_key] = {
                        "at": time.monotonic(),
                        "result": result,
                    }
            return result
    raise Context7PoolError("all Context7 accounts are unavailable", last_status)
