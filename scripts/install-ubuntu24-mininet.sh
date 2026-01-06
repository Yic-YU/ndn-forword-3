#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root (e.g., sudo $0)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  mininet \
  openvswitch-switch \
  iproute2 iputils-ping \
  tcpdump iperf3 ethtool net-tools socat \
  tmux jq

echo
echo "Installed Mininet + Open vSwitch + tools."
echo "Next:"
echo "  - Start OVS: systemctl enable --now openvswitch-switch   (or: service openvswitch-switch start)"
echo "  - Verify:    ovs-vsctl show"
echo "  - Mininet:   mn --switch ovsk --controller none --test pingall"
