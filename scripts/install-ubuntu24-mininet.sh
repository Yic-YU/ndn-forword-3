#!/usr/bin/env bash
set -euo pipefail

force_ovs=0
if [[ "${1:-}" == "--force-ovs" ]]; then
  force_ovs=1
fi

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root (e.g., sudo $0)" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

apt-get update

base_pkgs=(
  mininet
  iproute2 iputils-ping
  tcpdump iperf3 ethtool net-tools socat
  tmux jq
)

# Avoid mixing distro-packaged OVS with an existing /usr/local OVS install unless requested.
ovs_pkgs=(openvswitch-switch)
if command -v ovs-vsctl >/dev/null 2>&1 && [[ "${force_ovs}" -ne 1 ]]; then
  echo "Detected existing OVS: $(ovs-vsctl --version | head -n 1)"
  echo "Skipping apt installation of openvswitch-switch (use --force-ovs to install anyway)."
  ovs_pkgs=()
fi

apt-get install -y --no-install-recommends "${base_pkgs[@]}" "${ovs_pkgs[@]}"

echo
echo "Installed Mininet + Open vSwitch + tools."
echo "Next:"
echo "  - Start OVS: systemctl enable --now openvswitch-switch   (or: service openvswitch-switch start)"
echo "  - Verify:    ovs-vsctl show"
echo "  - Mininet:   mn --switch ovsk --controller none --test pingall"
