#!/usr/bin/env python3
"""Read host/container network interface counters for the Web dashboard."""

import os
import json
import subprocess
import time
import urllib.request


WIREGUARD_INTERFACES = {"wg0": "wg0", "wg1": "dev_wg"}
WIREGUARD_PEER_FRESH_SECONDS = 180


def configured_wireguard_probes(value=None):
    """Return explicitly configured display-name to peer-address probes."""
    configured = os.environ.get("EYES_WIREGUARD_PROBES", "") if value is None else value
    return dict(
        entry.split("=", 1) for entry in configured.split(",") if "=" in entry
    )


def mounted_filesystem_type(path, mountinfo_path="/proc/self/mountinfo"):
    """Return the filesystem type only when path is an explicit mount point."""
    target = os.path.normpath(path)
    try:
        with open(mountinfo_path, encoding="utf-8") as handle:
            for line in handle:
                fields = line.split()
                if "-" not in fields or len(fields) < 7:
                    continue
                mount_point = fields[4].replace("\\040", " ").replace("\\011", "\t")
                if os.path.normpath(mount_point) != target:
                    continue
                separator = fields.index("-")
                return fields[separator + 1] if len(fields) > separator + 1 else None
    except OSError:
        return None
    return None


def collect_wireguard_status(paths=None):
    """Return WireGuard interface presence and byte counters.

    Host counters are preferred when explicitly mounted; container counters are
    a fallback for host-network deployments.
    """
    paths = paths or ("/host_proc_net/dev", "/proc/net/dev")
    results = {
        display_name: {"ok": False, "tx_bytes": 0, "rx_bytes": 0, "ip": None}
        for display_name in WIREGUARD_INTERFACES
    }
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        for display_name, interface in WIREGUARD_INTERFACES.items():
            if results[display_name]["ok"]:
                continue
            for line in lines:
                name, separator, counters = line.partition(":")
                if not separator or name.strip() != interface:
                    continue
                parts = counters.split()
                results[display_name]["ok"] = True
                if len(parts) >= 16:
                    try:
                        results[display_name]["rx_bytes"] = int(parts[0])
                        results[display_name]["tx_bytes"] = int(parts[8])
                    except ValueError:
                        pass
                break
    return results


def merge_agent_wireguard_status(
    results, interfaces, now=None, fresh_seconds=None, probes=None
):
    """Merge root Agent peer handshakes into interface counters."""
    timestamp = int(time.time() if now is None else now)
    fresh_seconds = fresh_seconds or WIREGUARD_PEER_FRESH_SECONDS
    by_name = {
        item.get("name"): item for item in interfaces
        if isinstance(item, dict) and item.get("name")
    }
    for display_name, interface_name in WIREGUARD_INTERFACES.items():
        info = results[display_name]
        interface = by_name.get(interface_name)
        if not interface:
            info.update({
                "interface_up": False,
                "peer_online": False,
                "peers": [],
                "ok": False,
            })
            continue
        peers = []
        for peer in interface.get("peers", []):
            target = (probes or {}).get(display_name)
            allowed_ips = peer.get("allowed_ips", "")
            if target and target not in {
                allowed.strip().split("/", 1)[0]
                for allowed in allowed_ips.split(",")
            }:
                continue
            latest = int(peer.get("latest_handshake") or 0)
            age = max(0, timestamp - latest) if latest else None
            peers.append({
                "allowed_ips": allowed_ips,
                "handshake_age_seconds": age,
                "online": age is not None and age <= fresh_seconds,
            })
        peer_online = any(peer["online"] for peer in peers)
        info.update({
            "interface_up": bool(info.get("ok")),
            "peer_online": peer_online,
            "peers": peers,
            "ok": bool(info.get("ok")) and (peer_online if peers else False),
        })
    return results


def collect_wireguard_with_agent(agent_url, paths=None):
    """Collect interface counters and enrich them with Agent peer handshakes."""
    results = collect_wireguard_status(paths)
    if not agent_url:
        return results
    try:
        request = urllib.request.Request(f"{agent_url.rstrip('/')}/api/wireguard")
        with urllib.request.urlopen(request, timeout=5) as response:
            interfaces = json.loads(response.read().decode("utf-8"))
        if isinstance(interfaces, list):
            return merge_agent_wireguard_status(
                results, interfaces, probes=configured_wireguard_probes()
            )
    except Exception:
        pass
    return probe_wireguard_reachability(results)


def probe_wireguard_reachability(results, probes=None, runner=None):
    """Fallback peer reachability when the root Agent endpoint is unavailable."""
    if probes is None:
        probes = configured_wireguard_probes()
    runner = runner or subprocess.run
    for display_name, target in probes.items():
        if display_name not in results:
            continue
        try:
            response = runner(
                [
                    "ping", "-I", WIREGUARD_INTERFACES[display_name],
                    "-c", "1", "-W", "1", target,
                ],
                capture_output=True, text=True, timeout=3,
            )
            online = response.returncode == 0
        except Exception:
            online = False
        info = results[display_name]
        info.update({
            "interface_up": bool(info.get("ok")),
            "peer_online": online,
            "peers": [{
                "allowed_ips": target,
                "handshake_age_seconds": None,
                "online": online,
                "status_source": "reachability",
            }],
            "ok": bool(info.get("ok")) and online,
        })
    return results
