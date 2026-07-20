#!/usr/bin/env python3
"""Local Hub runtime observer for the Fleet control plane."""

import os
import platform
import shutil
import socket
import time
from datetime import datetime, timezone

from fleet import ensure_local_hub_node, put_snapshot, record_heartbeat


PROTOCOL_VERSION = "eyes.node.v1"


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _boot_id():
    try:
        with open("/proc/sys/kernel/random/boot_id", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return f"hub-runtime-{platform.node()}"


def _memory():
    values = {}
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    return values.get("MemTotal", 0), values.get("MemAvailable", 0)


def _addresses():
    addresses = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            address = info[4][0]
            if address not in addresses:
                addresses.append(address)
    except OSError:
        pass
    return addresses


def collect_hub_inventory():
    uptime = None
    try:
        with open("/proc/uptime", encoding="utf-8") as handle:
            uptime = int(float(handle.read().split()[0]))
    except (OSError, ValueError):
        pass
    capabilities = [
        {"name": "eyes.io/system.observe", "version": "v1", "health": "ready"},
        {"name": "eyes.io/control-plane.hub", "version": "v1alpha1", "health": "ready"},
    ]
    return {
        "system": {
            "hostname": socket.gethostname(),
            "uptime_seconds": uptime,
            "timestamp": _utc_now(),
        },
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "network": {"addresses": _addresses()},
        "systemd": [],
        "capabilities": capabilities,
        "observation_scope": "hub-runtime",
    }


def collect_hub_resources():
    memory_total, memory_available = _memory()
    disk = shutil.disk_usage("/")
    cpu_count = os.cpu_count() or 1
    return {
        "cpu": {
            "capacity_millis": cpu_count * 1000,
            "allocatable_millis": cpu_count * 1000,
            "load_1m": os.getloadavg()[0] if hasattr(os, "getloadavg") else None,
        },
        "memory": {
            "capacity_bytes": memory_total,
            "allocatable_bytes": memory_total,
            "available_bytes": memory_available,
        },
        "filesystem": {
            "root": {"capacity_bytes": disk.total, "available_bytes": disk.free}
        },
        "observation_scope": "hub-runtime",
    }


def refresh_local_hub_node():
    """Publish a heartbeat and current Hub runtime snapshots."""
    node_id = ensure_local_hub_node()
    observed_at = _utc_now()
    record_heartbeat(
        node_id,
        {
            "boot_id": _boot_id(),
            "sequence": time.monotonic_ns(),
            "agent_version": "hub-runtime",
            "protocol_version": PROTOCOL_VERSION,
        },
    )
    generation = time.time_ns()
    put_snapshot(node_id, "inventory", generation, collect_hub_inventory(), observed_at)
    put_snapshot(node_id, "resources", generation + 1, collect_hub_resources(), observed_at)
    return node_id
