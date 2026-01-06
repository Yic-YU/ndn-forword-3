#!/usr/bin/env python3
import argparse
import os
import shutil
import signal
import sys
import textwrap
import threading
import time

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel, warn
from mininet.net import Mininet


def _alloc_p2p_subnet(index: int):
    # /30 blocks: ...0, ...4, ...8 ...
    third = index // 64
    fourth = (index % 64) * 4
    base = f"10.0.{third}.{fourth}"
    ip1 = f"10.0.{third}.{fourth + 1}"
    ip2 = f"10.0.{third}.{fourth + 2}"
    cidr = f"{base}/30"
    return cidr, ip1, ip2


def _find_ndnd(explicit: str | None, repo_root: str) -> str:
    if explicit:
        p = explicit
        if not os.path.isabs(p):
            p = os.path.abspath(p)
        if not os.path.exists(p):
            raise FileNotFoundError(f"--ndnd not found: {p}")
        return p

    p = shutil.which("ndnd")
    if p:
        return p

    p = os.path.join(repo_root, "ndnd", "ndnd")
    if os.path.exists(p):
        return p

    raise FileNotFoundError(
        "Cannot find ndnd binary. Build it with `make -C ndnd` or pass `--ndnd /path/to/ndnd`."
    )


def _write_combined_conf(conf_path: str, sock_path: str, router: str, network: str, udp_port: int):
    # NOTE: multiple daemons on one machine must NOT share the default unix socket path.
    content = f"""\
dv:
  network: {network}
  router: {router}
  keychain: "insecure"

fw:
  faces:
    udp:
      enabled_unicast: true
      enabled_multicast: false
      port_unicast: {udp_port}
    tcp:
      enabled: false
    unix:
      enabled: true
      socket_path: {sock_path}
    websocket:
      enabled: false
  fw:
    threads: 2
"""
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_host_wrapper(wrapper_path: str, ndnd_bin: str, state_dir: str):
    content = f"""\
#!/usr/bin/env sh
set -eu

# Mininet hosts usually keep the system hostname, so we detect the Mininet node
# name from interface names like "g1-eth0", "s2-eth1", etc.
if [ -z "${{NDN_CLIENT_TRANSPORT:-}}" ]; then
  node="$(
    ip -o link show 2>/dev/null \
      | awk -F': ' '{{print $2}}' \
      | sed 's/@.*$//' \
      | sed -n 's/^\\([A-Za-z0-9_][A-Za-z0-9_]*\\)-eth[0-9][0-9]*$/\\1/p' \
      | head -n 1
  )"
  if [ -n "${{node:-}}" ] && [ -S "{state_dir}/$node.sock" ]; then
    export NDN_CLIENT_TRANSPORT="unix://{state_dir}/$node.sock"
  else
    echo "ndndctl: cannot auto-detect socket; set NDN_CLIENT_TRANSPORT=unix://{state_dir}/<node>.sock" >&2
    echo "ndndctl: available sockets:" >&2
    ls -1 "{state_dir}"/*.sock 2>/dev/null || true
    exit 2
  fi
fi
exec "{ndnd_bin}" "$@"
"""
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(wrapper_path, 0o755)


def _tc_link_kwargs(*, bw: float | None, delay: str | None, jitter: str | None, loss: float | None, queue: int | None):
    kwargs: dict[str, object] = {}
    if bw is not None:
        kwargs["bw"] = bw
        kwargs["use_htb"] = True
    if delay:
        kwargs["delay"] = delay
    if jitter:
        kwargs["jitter"] = jitter
    if loss is not None:
        kwargs["loss"] = loss
    if queue is not None:
        kwargs["max_queue_size"] = queue
    return kwargs


def _ensure_root():
    if os.geteuid() != 0:
        raise PermissionError("Mininet requires root. Run with: sudo python3 scripts/mn-ndnd.py ...")


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Run a small NDN network (ndnd) in Mininet, with satellite-like link properties.

            Topology: g1 -- s1 -- s2 -- s3 -- g2, plus optional access handover links.
            - g1 can connect to s1 and/or s2 (handover simulation)
            - g2 can connect to s2 and/or s3
            """
        ),
    )
    parser.add_argument("--ndnd", help="Path to ndnd binary (default: PATH or ./ndnd/ndnd)")
    parser.add_argument("--state-dir", default="/tmp/ndn-mn", help="Where to store per-node configs/sockets/logs")
    parser.add_argument("--network", default="/satnet", help="DV network prefix (same for all nodes)")
    parser.add_argument("--udp-port", type=int, default=6363, help="UDP port for ndnd faces")
    parser.add_argument("--cli", action="store_true", help="Enter Mininet CLI after startup")

    # Link parameters (reasonable LEO-ish defaults; tweak as needed)
    parser.add_argument("--access-bw", type=float, default=20, help="Access link bandwidth (Mbit/s)")
    parser.add_argument("--access-delay", default="25ms", help="Access link one-way delay (e.g. 25ms)")
    parser.add_argument("--access-jitter", default="2ms", help="Access link delay jitter (e.g. 2ms)")
    parser.add_argument("--access-loss", type=float, default=0.2, help="Access link loss percent (e.g. 0.2)")

    parser.add_argument("--isl-bw", type=float, default=50, help="Inter-satellite link bandwidth (Mbit/s)")
    parser.add_argument("--isl-delay", default="8ms", help="Inter-satellite link one-way delay (e.g. 8ms)")
    parser.add_argument("--isl-jitter", default="1ms", help="Inter-satellite link delay jitter (e.g. 1ms)")
    parser.add_argument("--isl-loss", type=float, default=0.05, help="Inter-satellite link loss percent (e.g. 0.05)")

    parser.add_argument("--queue", type=int, default=200, help="Link queue size (packets)")

    # Handover simulation: switch g1 from s1 to s2 after N seconds (and g2 from s3 to s2).
    parser.add_argument("--handover-after", type=float, default=0.0, help="Seconds until handover (0 disables)")
    args = parser.parse_args()

    _ensure_root()
    setLogLevel("info")

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ndnd_bin = _find_ndnd(args.ndnd, repo_root)
    state_dir = os.path.abspath(args.state_dir)
    os.makedirs(state_dir, exist_ok=True)

    wrapper_path = os.path.join(state_dir, "ndndctl")
    _write_host_wrapper(wrapper_path, ndnd_bin, state_dir)

    net = Mininet(controller=None, link=TCLink, autoSetMacs=True, autoStaticArp=True)
    nodes = {name: net.addHost(name) for name in ("g1", "g2", "s1", "s2", "s3")}

    links: list[dict[str, object]] = []
    subnet_idx = 0

    def add_p2p(a: str, b: str, *, kind: str):
        nonlocal subnet_idx
        cidr, a_ip, b_ip = _alloc_p2p_subnet(subnet_idx)
        subnet_idx += 1

        if kind == "access":
            kw = _tc_link_kwargs(
                bw=args.access_bw,
                delay=args.access_delay,
                jitter=args.access_jitter,
                loss=args.access_loss,
                queue=args.queue,
            )
        elif kind == "isl":
            kw = _tc_link_kwargs(
                bw=args.isl_bw,
                delay=args.isl_delay,
                jitter=args.isl_jitter,
                loss=args.isl_loss,
                queue=args.queue,
            )
        else:
            raise ValueError(f"unknown link kind: {kind}")

        link = net.addLink(
            nodes[a],
            nodes[b],
            cls=TCLink,
            params1={"ip": f"{a_ip}/30"},
            params2={"ip": f"{b_ip}/30"},
            **kw,
        )
        links.append(
            {
                "a": a,
                "b": b,
                "a_ip": a_ip,
                "b_ip": b_ip,
                "cidr": cidr,
                "kind": kind,
                "link": link,
            }
        )

    # Inter-satellite backbone
    add_p2p("s1", "s2", kind="isl")
    add_p2p("s2", "s3", kind="isl")

    # Access links (we create both options to allow handover simulation)
    add_p2p("g1", "s1", kind="access")
    add_p2p("g1", "s2", kind="access")
    add_p2p("g2", "s2", kind="access")
    add_p2p("g2", "s3", kind="access")

    net.start()

    # Default: g1<->s1 and g2<->s3 are up; alternate links are down (ready for handover).
    net.configLinkStatus("g1", "s2", "down")
    net.configLinkStatus("g2", "s2", "down")

    procs = {}

    def cleanup():
        for name, proc in list(procs.items()):
            try:
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
            procs.pop(name, None)
        try:
            net.stop()
        except Exception:
            pass

    try:
        # Start ndnd on every node with unique unix socket + config.
        for name in nodes.keys():
            sock_path = os.path.join(state_dir, f"{name}.sock")
            conf_path = os.path.join(state_dir, f"{name}.yml")
            log_path = os.path.join(state_dir, f"{name}.log")

            try:
                os.unlink(sock_path)
            except FileNotFoundError:
                pass

            _write_combined_conf(
                conf_path=conf_path,
                sock_path=sock_path,
                router=f"{args.network}/{name}",
                network=args.network,
                udp_port=args.udp_port,
            )
            procs[name] = nodes[name].popen(f'"{ndnd_bin}" daemon "{conf_path}" >"{log_path}" 2>&1', shell=True)

        # Wait for all unix sockets to appear (daemon ready).
        deadline = time.time() + 8
        missing = []
        while time.time() < deadline:
            missing = [name for name in nodes.keys() if not os.path.exists(os.path.join(state_dir, f"{name}.sock"))]
            if not missing:
                break
            time.sleep(0.1)
        if missing:
            warn(f"Some ndnd sockets not ready: {missing}\n")

        # Create DV neighbor relationships for all links that start 'up'.
        def ndndctl(hostname: str) -> str:
            return f'"{wrapper_path}"'

        for l in links:
            a = str(l["a"])
            b = str(l["b"])
            a_ip = str(l["a_ip"])
            b_ip = str(l["b_ip"])
            # Only link-create for the currently-up access edges.
            if {a, b} == {"g1", "s2"} or {a, b} == {"g2", "s2"}:
                continue
            nodes[a].cmd(f'{ndndctl(a)} dv link-create "udp://{b_ip}:{args.udp_port}" >/dev/null 2>&1 || true')
            nodes[b].cmd(f'{ndndctl(b)} dv link-create "udp://{a_ip}:{args.udp_port}" >/dev/null 2>&1 || true')

        if args.handover_after > 0:
            def handover():
                time.sleep(args.handover_after)
                info(f"*** Handover: switching g1 access from s1->s2 and g2 from s3->s2 (after {args.handover_after}s)\n")
                net.configLinkStatus("g1", "s1", "down")
                net.configLinkStatus("g1", "s2", "up")
                net.configLinkStatus("g2", "s3", "down")
                net.configLinkStatus("g2", "s2", "up")

                # Ensure neighbor relationships exist for the newly-up links.
                for l in links:
                    a = str(l["a"])
                    b = str(l["b"])
                    if {a, b} not in ({"g1", "s2"}, {"g2", "s2"}):
                        continue
                    a_ip = str(l["a_ip"])
                    b_ip = str(l["b_ip"])
                    nodes[a].cmd(f'{ndndctl(a)} dv link-create "udp://{b_ip}:{args.udp_port}" >/dev/null 2>&1 || true')
                    nodes[b].cmd(f'{ndndctl(b)} dv link-create "udp://{a_ip}:{args.udp_port}" >/dev/null 2>&1 || true')

            threading.Thread(target=handover, daemon=True).start()

        info("\n*** ndnd is running on all nodes.\n")
        info(f"*** Per-node state in: {state_dir}\n")
        info(f"*** In Mininet CLI, use: <node> {wrapper_path} <ndnd-subcommand>\n")
        info(f'*** Example: g1 {wrapper_path} put -expose /g1/hello < /tmp/hello.txt\n')
        info(f'*** Example: g2 {wrapper_path} cat /g1/hello > /tmp/out.txt\n\n')

        if args.cli:
            CLI(net)
        else:
            info("Skipping Mininet CLI (use --cli to enter interactive mode). Sleeping forever...\n")
            while True:
                time.sleep(3600)

    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
