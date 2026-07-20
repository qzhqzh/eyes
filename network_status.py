#!/usr/bin/env python3
"""Read host/container network interface counters for the Web dashboard."""


WIREGUARD_INTERFACES = {"wg0": "wg0", "wg1": "dev_wg"}


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
