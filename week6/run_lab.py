#!/usr/bin/env python3
"""Parts 1–6, inside a fresh privileged course container (not the laptop network)."""
import contextlib
from pathlib import Path
import shlex
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_overlay import NO_OFFLOAD
from week6.run_assignment import boundary, capture, command, ping, throughput
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.nodelib import LinuxBridge
from mininet.topo import SingleSwitchTopo


def root(cmd, required=True):
    print('$ ' + cmd, flush=True)
    result = subprocess.run(['sh', '-c', cmd], capture_output=True, text=True)
    print((result.stdout + result.stderr).rstrip(), flush=True)
    print(f'[exit status {result.returncode}]', flush=True)
    if required and result.returncode:
        raise RuntimeError(cmd)


def manual():
    print('\nPART 2: manual namespaces and bridge', flush=True)
    try:
        for cmd in [
            'ip netns add red', 'ip netns add blue',
            'ip link add br0 type bridge', 'ip link set br0 up',
            'ip link add redlink type veth peer name redeth',
            'ip link add bluelink type veth peer name blueeth',
            'ip link set redeth netns red', 'ip link set blueeth netns blue',
            'ip link set redlink master br0', 'ip link set bluelink master br0',
            'ip link set redlink up', 'ip link set bluelink up',
            'ip -n red link set lo up', 'ip -n blue link set lo up',
            'ip -n red addr add 10.45.9.1/24 dev redeth',
            'ip -n blue addr add 10.45.9.2/24 dev blueeth',
            'ip -n red link set redeth up', 'ip -n blue link set blueeth up',
            'ip netns exec red ping -n -c 3 -W 1 10.45.9.2',
            'ip -n red -br link', 'ip -n blue -br link', 'bridge fdb show br br0',
        ]:
            root(cmd)
    finally:
        for cmd in ['ip netns del red', 'ip netns del blue', 'ip link del br0']:
            root(cmd, required=False)


def tunnels():
    net = Mininet(topo=SingleSwitchTopo(k=2), controller=None, switch=LinuxBridge, ipBase='10.45.0.0/24')
    try:
        net.start()
        h1, h2 = net['h1'], net['h2']
        print('\nPART 1: Mininet namespaces and veth links', flush=True)
        root('lsns -t net')
        for h in [h1, h2]:
            print(f'{h.name} shell PID={h.pid}', flush=True)
            root(f'readlink /proc/{h.pid}/ns/net; ps -p {h.pid} -o pid,ppid,comm,args')
            command(h, 'ip -br link; ip -br address; ip -o link')
            command(h, f'python3 -c {shlex.quote(NO_OFFLOAD)} {h.name}-eth0')
        root('ip -o link; bridge link show')
        ping(h1, '10.45.0.2', expected=True)
        print('\nPART 3: IPv4 VXLAN', flush=True)
        for h, local, remote, overlay in [(h1, '10.45.0.1', '10.45.0.2', '10.45.100.1'), (h2, '10.45.0.2', '10.45.0.1', '10.45.100.2')]:
            command(h, f'ip link add vx100 type vxlan id 100 local {local} remote {remote} dstport 4789 dev {h.name}-eth0')
            command(h, f'ip addr add {overlay}/24 dev vx100; ip link set vx100 up; ip -d link show vx100')
            command(h, f'python3 -c {shlex.quote(NO_OFFLOAD)} vx100')
        with capture(h2, 'h2-eth0', 'udp port 4789'):
            ping(h1, '10.45.100.2', expected=True)
        print('\nPART 4: IPv4 MTU and throughput', flush=True)
        ping(h1, '10.45.0.2', 1472, expected=True)
        ping(h1, '10.45.0.2', 1473, expected=False)
        ping(h1, '10.45.100.2', 1422, expected=True)
        ping(h1, '10.45.100.2', 1423, expected=False)
        throughput(h1, h2, '10.45.0.2')
        throughput(h1, h2, '10.45.100.2')
        print('\nPART 5: IPv6 underlay', flush=True)
        for h, local, remote, overlay in [(h1, 'fd00:1945::1', 'fd00:1945::2', '10.45.106.1'), (h2, 'fd00:1945::2', 'fd00:1945::1', '10.45.106.2')]:
            command(h, f'ip -6 addr add {local}/64 dev {h.name}-eth0 nodad')
            command(h, f'ip link add vx106 type vxlan id 106 local {local} remote {remote} dstport 4789 dev {h.name}-eth0')
            command(h, f'ip addr add {overlay}/24 dev vx106; ip link set vx106 up; ip -d link show vx106')
        command(h1, 'ping -6 -n -c 2 -W 1 fd00:1945::2')
        with capture(h2, 'h2-eth0', 'ip6 and udp port 4789'):
            ping(h1, '10.45.106.2', expected=True)
        ping(h1, '10.45.106.2', 1402, expected=True)
        ping(h1, '10.45.106.2', 1403, expected=False)
        print('\nPART 6: receive-side underlay MTU mismatch', flush=True)
        command(h2, 'ip link set h2-eth0 mtu 1400; ip -s -s link show h2-eth0; nstat -az')
        ping(h1, '10.45.100.2', 56, expected=True)
        ping(h1, '10.45.100.2', 1422, expected=False)
        boundary(h1, '10.45.100.2', 56, 1423)
        throughput(h1, h2, '10.45.100.2')
        command(h2, 'ip -s -s link show h2-eth0; nstat -az')
        command(h2, 'ip link set h2-eth0 mtu 1500; ip -br link')
        ping(h1, '10.45.100.2', 1422, expected=True)
        throughput(h1, h2, '10.45.100.2')
    finally:
        net.stop()


def main():
    setLogLevel('warning')
    with open('evidence6/lab.txt', 'w') as output, contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        manual()
        tunnels()
    print('Wrote evidence6/lab.txt', flush=True)


if __name__ == '__main__':
    main()
