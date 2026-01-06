# ndn-forward3

本仓库用于在本机/Mininet 环境中运行 `ndnd`（Named Data Networking Daemon）。

## 环境信息（你当前）

- OS: Ubuntu 24.04 LTS（WSL2）
- OVS: `ovs-vsctl (Open vSwitch) 2.17.9`
- `ndnd` 可执行文件：`/home/yic/chensing/ndn-forward3/ndnd/ndnd`

## 安装 Mininet + 常用工具（Ubuntu 24.04）

推荐直接用 APT 安装。

```bash
sudo apt update
sudo apt install -y \
  mininet \
  openvswitch-switch \
  iproute2 iputils-ping \
  tcpdump iperf3 ethtool net-tools socat \
  tmux jq
```

如果你已经通过其它方式（例如源码/`/usr/local`）安装了 OVS，为避免“混装”导致的路径/服务冲突，可以先不装 `openvswitch-switch`，仅安装 `mininet` 和工具即可。

可选：如果你需要抓包 GUI，可以安装 `wireshark`（WSL2 下一般更推荐用 `tcpdump`/`tshark`）。

### 启动/检查 Open vSwitch

在普通 Ubuntu 上：

```bash
sudo systemctl enable --now openvswitch-switch
sudo ovs-vsctl show
```

在 WSL2 上如果 `systemctl` 不可用，可尝试：

```bash
sudo service openvswitch-switch start
sudo ovs-vsctl show
```

如果两种方式都不行，通常是 WSL2 未启用 systemd：在 `/etc/wsl.conf` 配置 `systemd=true` 后重启 WSL。

### 验证 Mininet 可用

```bash
sudo mn --switch=ovsk,failMode=standalone --controller=none --test pingall --twait 2
```

如果 `--switch=ovsk,failMode=standalone` 报错（常见于内核/OVS datapath 不匹配的环境），可以先用默认 switch 验证 Mininet 基本功能：

```bash
sudo mn --controller none --test pingall
```

## 一键安装脚本

见 `scripts/install-ubuntu24-mininet.sh`。
