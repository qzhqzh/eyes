#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "eyes-agent installer must run as root" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required; install it with the OpenWrt package manager" >&2
    exit 1
fi

if ! python3 -c 'import json, ssl, tempfile, urllib.request' >/dev/null 2>&1; then
    echo "python3 ssl/urllib modules are required" >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

mkdir -p /opt/eyes/agent /etc/eyes /var/lib/eyes
cp "$script_dir/eyes-agent.py" /opt/eyes/agent/eyes-agent.py
cp "$script_dir/node_client.py" /opt/eyes/agent/node_client.py
cp "$script_dir/eyes-agent.openwrt.init" /etc/init.d/eyes-agent
chmod 0755 /opt/eyes/agent/eyes-agent.py /etc/init.d/eyes-agent
chmod 0644 /opt/eyes/agent/node_client.py
chmod 0700 /etc/eyes /var/lib/eyes

if [ ! -e /etc/eyes/agent.env ]; then
    cp "$script_dir/agent.env.example" /etc/eyes/agent.env
fi

chown root:root /etc/eyes/agent.env
chmod 0600 /etc/eyes/agent.env

/etc/init.d/eyes-agent enable
echo "Installed eyes-agent for OpenWrt. Edit /etc/eyes/agent.env, then run:"
echo "  /etc/init.d/eyes-agent start"
