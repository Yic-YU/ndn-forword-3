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

## 用 Mininet 模拟“卫星网络” NDN（高时延/丢包/切换）

核心思路：

1) 用 Mininet 的 `TCLink` 给链路加 **带宽/时延/抖动/丢包/队列**（`tc netem`）。  
2) 在每个 Mininet host 里各自启动一个 `ndnd daemon`，并给每个实例配置 **不同的 Unix socket**（同机多实例不能共用 `/run/nfd/nfd.sock`）。  
3) 用 `ndnd dv link-create udp://<邻居IP>:6363` 建立邻居关系，让 DV 自动收敛；再用 `ndnd put/cat` 做内容发布/拉取。

### 1) 编译 `ndnd`（如果还没编译）

```bash
make -C ndnd
```

### 2) 启动卫星拓扑（含可选切换）

脚本：`scripts/mn-ndnd.py`

```bash
sudo python3 scripts/mn-ndnd.py --cli
```

默认拓扑（LEO 风格参数，可在命令行改）：

- `g1 -- s1 -- s2 -- s3 -- g2`（ISL：较低时延/丢包）
- `g1` 还有一条备用接入链路到 `s2`，`g2` 还有一条备用接入链路到 `s2`
- 默认仅 `g1<->s1`、`g2<->s3` 接入链路为 up；备用链路为 down

模拟“切换”（handover），例如 30 秒后把 `g1` 从 `s1` 切到 `s2`、把 `g2` 从 `s3` 切到 `s2`：

```bash
sudo python3 scripts/mn-ndnd.py --cli --handover-after 30
```

### 3) 在 Mininet CLI 里跑 NDN

脚本会在 `--state-dir`（默认 `/tmp/ndn-mn`）里生成一个封装命令 `ndndctl`，自动为当前 host 选择正确的 socket（等价于设置 `NDN_CLIENT_TRANSPORT=unix://...`）。

示例（在 Mininet CLI 里）：

```bash
mininet> g1 /tmp/ndn-mn/ndndctl put -expose /g1/hello < /tmp/hello.txt
mininet> g2 /tmp/ndn-mn/ndndctl cat /g1/hello > /tmp/out.txt
mininet> g2 cat /tmp/out.txt
```

### 4) 调参建议（卫星链路常用）

- LEO：`--access-delay 20ms~50ms`，`--isl-delay 5ms~15ms`
- GEO：把接入链路时延提高到 `--access-delay 250ms`（单程）级别
- 丢包/抖动：`--access-loss/--access-jitter`、`--isl-loss/--isl-jitter`
- 带宽/队列：`--access-bw/--isl-bw`、`--queue`
