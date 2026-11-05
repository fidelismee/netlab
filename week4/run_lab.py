#!/usr/bin/env python3
"""Run and print the Week 4 OpenFlow experiments in a Mininet environment."""
import subprocess
import time
from functools import partial

from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch
from mininet.topo import SingleSwitchTopo


def heading(title):
    print(f"\n===== {title} =====", flush=True)


def root_command(*args):
    print("$", " ".join(args), flush=True)
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout.rstrip(), flush=True)
    print(f"[exit status {result.returncode}]", flush=True)
    return result


def host_command(host, command):
    print(f"{host.name}$ {command}", flush=True)
    print(host.cmd(command).rstrip(), flush=True)


def ping_all(net):
    print("mininet> pingall", flush=True)
    dropped = net.pingAll()
    print(f"pingall returned {dropped:.0f}% dropped", flush=True)


def capture_on_h3(h1, h3, destination):
    print("h3$ timeout 4 tcpdump -ni h3-eth0 icmp", flush=True)
    capture = h3.popen(
        ["timeout", "4", "tcpdump", "-ni", "h3-eth0", "icmp"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    time.sleep(0.25)
    host_command(h1, f"ping -c 3 {destination}")
    output, _ = capture.communicate(timeout=6)
    print("--- h3 tcpdump output ---", flush=True)
    print(output.rstrip(), flush=True)


def main():
    setLogLevel("info")
    switch = partial(OVSSwitch, datapath="user")
    net = Mininet(
        topo=SingleSwitchTopo(k=3),
        switch=switch,
        controller=None,
        autoSetMacs=True,
        ipBase="10.45.0.0/16",
    )
    controller = None
    try:
        net.start()
        h1, h2, h3 = (net.get(name) for name in ("h1", "h2", "h3"))

        heading("TOPOLOGY AND ADDRESSES")
        print("nodes:", " ".join(node.name for node in net.values()), flush=True)
        for host in (h1, h2, h3):
            host_command(host, f"ip -brief address show dev {host.name}-eth0")
        root_command("ovs-ofctl", "show", "s1")

        heading("STEP 0: EMPTY SWITCH")
        root_command("ovs-ofctl", "show", "s1")
        root_command("ovs-ofctl", "dump-flows", "s1")
        host_command(h1, "ping -c 2 10.45.0.2")

        heading("STEP 1: HUB")
        root_command("ovs-ofctl", "add-flow", "s1", "actions=flood")
        ping_all(net)
        root_command("ovs-ofctl", "dump-flows", "s1")
        capture_on_h3(h1, h3, "10.45.0.2")
        root_command("ovs-ofctl", "dump-flows", "s1")

        heading("STEP 2: MANUAL FORWARDING")
        root_command("ovs-ofctl", "del-flows", "s1")
        root_command("ovs-ofctl", "add-flow", "s1", "arp,actions=flood")
        for port in range(1, 4):
            root_command(
                "ovs-ofctl",
                "add-flow",
                "s1",
                f"dl_dst=00:00:00:00:00:0{port},actions=output:{port}",
            )
        ping_all(net)
        root_command("ovs-ofctl", "dump-flows", "s1")
        capture_on_h3(h1, h3, "10.45.0.2")
        root_command("ovs-ofctl", "dump-flows", "s1")

        heading("STEP 3A: DEFAULT-PRIORITY FIREWALL")
        root_command(
            "ovs-ofctl",
            "add-flow",
            "s1",
            "icmp,nw_src=10.45.0.1,nw_dst=10.45.0.3,actions=drop",
        )
        host_command(h1, "ping -c 3 10.45.0.3")
        root_command("ovs-ofctl", "dump-flows", "s1")

        heading("STEP 3B: HIGH-PRIORITY FIREWALL")
        root_command(
            "ovs-ofctl",
            "--strict",
            "del-flows",
            "s1",
            "icmp,nw_src=10.45.0.1,nw_dst=10.45.0.3",
        )
        root_command(
            "ovs-ofctl",
            "add-flow",
            "s1",
            "priority=40000,icmp,nw_src=10.45.0.1,nw_dst=10.45.0.3,actions=drop",
        )
        host_command(h1, "ping -c 3 10.45.0.3")
        host_command(h1, "ping -c 3 10.45.0.2")
        host_command(h3, "ping -c 3 10.45.0.1")
        root_command("ovs-ofctl", "dump-flows", "s1")

        heading("STEP 4: CONNECT THE CONTROLLER")
        print("$ ovs-testcontroller ptcp:6653 &", flush=True)
        controller = subprocess.Popen(
            ["ovs-testcontroller", "ptcp:6653"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(1)
        root_command("ovs-ofctl", "del-flows", "s1")
        root_command("ovs-vsctl", "set-controller", "s1", "tcp:127.0.0.1:6653")
        time.sleep(1)
        root_command("ovs-vsctl", "show")
        host_command(h1, "ping -c 3 10.45.0.2")
        host_command(h2, "ping -c 3 10.45.0.3")
        root_command("ovs-ofctl", "dump-flows", "s1")

        heading("STEP 5: CONTROLLER FAILURE")
        print("$ terminate ovs-testcontroller", flush=True)
        controller.terminate()
        controller.wait(timeout=5)
        controller = None
        time.sleep(1)
        root_command("ovs-vsctl", "list", "controller")
        host_command(h1, "ping -c 3 10.45.0.2")
        host_command(h1, "ping -c 3 10.45.0.3")
        root_command("ovs-ofctl", "dump-flows", "s1")
        print("Waiting 70 seconds for reactive forwarding flows to expire...", flush=True)
        time.sleep(70)
        host_command(h1, "ping -c 3 10.45.0.2")
        root_command("ovs-ofctl", "dump-flows", "s1")

        heading("STEP 6: STANDALONE FAIL MODE")
        root_command("ovs-vsctl", "set-fail-mode", "s1", "standalone")
        root_command("ovs-vsctl", "get-fail-mode", "s1")
        print("Waiting 15 seconds for standalone fallback...", flush=True)
        time.sleep(15)
        host_command(h1, "ping -c 2 10.45.0.3")
        root_command("ovs-ofctl", "dump-flows", "s1")
    finally:
        if controller is not None:
            controller.terminate()
            try:
                controller.wait(timeout=5)
            except subprocess.TimeoutExpired:
                controller.kill()
        net.stop()


if __name__ == "__main__":
    main()
