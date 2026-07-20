#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "eyes-agent installer must run as root" >&2
    exit 1
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

install -d -m 0755 /opt/eyes/agent /etc/eyes
install -m 0755 "$script_dir/eyes-agent.py" /opt/eyes/agent/eyes-agent.py
install -m 0644 "$script_dir/node_client.py" /opt/eyes/agent/node_client.py
install -m 0644 "$script_dir/eyes-agent.service" /etc/systemd/system/eyes-agent.service

if [ ! -e /etc/eyes/agent.env ]; then
    install -m 0600 "$script_dir/agent.env.example" /etc/eyes/agent.env
fi

systemctl daemon-reload
echo "Installed eyes-agent. Edit /etc/eyes/agent.env, then run:"
echo "  systemctl enable --now eyes-agent"
