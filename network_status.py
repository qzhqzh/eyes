#!/usr/bin/env python3
"""Read host/container network interface counters for the Web dashboard."""

import os


WIREGUARD_INTERFACES = {"wg0": "wg0", "wg1": "dev_wg"}


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
