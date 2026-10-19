#!/usr/bin/env python3
"""Build a Mininet network from a YAML or JSON description, then open the Mininet CLI.

Run it inside the lab container, from the folder holding your files:
    python3 build_topo.py topology.yaml
    python3 build_topo.py topology.json
"""
import ipaddress
import json
import sys

import yaml
from mininet.cli import CLI
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.nodelib import LinuxBridge


def load(path):
    """Read the network description. Same data model, two possible serialisations."""
    with open(path) as f:
        if path.endswith(".json"):
            return json.load(f)
        return yaml.safe_load(f)


def check_mine(spec):
    """Return problems with the student's own addresses (supplied — you don't need to change it).

    Every lab this semester uses addresses from your own blocks:
    IPv4 10.NN.0.0/16 and IPv6 fd00:NNNN::/32, from the last digits of your student ID.
    """
    last4 = str(spec.get("student_id_last4", ""))
    if len(last4) != 4 or not last4.isdigit():
        return ['student_id_last4 must be the last 4 digits of your student ID, in quotes, e.g. "4207"']
    v4_block = ipaddress.ip_network(f"10.{int(last4[2:])}.0.0/16")
    v6_block = ipaddress.ip_network(f"fd00:{last4}::/32")

    problems = []
    for host in spec["hosts"]:
        for key, block in (("ip", v4_block), ("ipv6", v6_block)):
            if key not in host:
                continue
            try:
                address = ipaddress.ip_interface(host[key]).ip
            except ValueError:
                problems.append(f"{host['name']}: {host[key]} isn't a valid address (still NN or NNNN?)")
                continue
            if address not in block:
                problems.append(f"{host['name']}: {address} isn't in your block {block}")
    return problems


def check(spec):
    """Return a list of problems in the description (an empty list means it looks fine).

    Checks:
    1. No IPv4 or IPv6 address is used by more than one host.
    2. Every link refers to a host or switch that actually exists.
    """
    problems = []
    seen = {}

    # Check for duplicate IPv4 and IPv6 addresses
    for host in spec["hosts"]:
        for key in ("ip", "ipv6"):
            if key not in host:
                continue

            address = str(ipaddress.ip_interface(host[key]).ip)

            if address in seen:
                problems.append(
                    f"{host['name']} and {seen[address]} both use {address}"
                )
            else:
                seen[address] = host["name"]

    # Build a set containing every valid node name
    nodes = set(spec["switches"])
    nodes.update(host["name"] for host in spec["hosts"])

    # Check that every link refers to existing nodes
    for a, b in spec["links"]:
        if a not in nodes:
            problems.append(f"link refers to unknown node {a}")
        if b not in nodes:
            problems.append(f"link refers to unknown node {b}")

    return problems


def build(spec):
    """Turn the description into a Mininet network: switches, then hosts, then links."""
    net = Mininet(switch=LinuxBridge, controller=None, autoSetMacs=True)
    for name in spec["switches"]:
        net.addSwitch(name)
    for host in spec["hosts"]:
        net.addHost(host["name"], ip=host["ip"])
    for a, b in spec["links"]:
        net.addLink(a, b)
    return net


def add_ipv6(net, spec):
    """Mininet only sets IPv4 addresses, so add each host's IPv6 address once the network is up."""
    for host in spec["hosts"]:
        if "ipv6" in host:
            node = net.get(host["name"])
            node.cmd(f"ip -6 addr add {host['ipv6']} dev {node.defaultIntf()}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 build_topo.py <topology.yaml|topology.json>")
    spec = load(sys.argv[1])

    problems = check_mine(spec) + check(spec)
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        sys.exit("Fix the description and try again.")

    setLogLevel("info")
    net = build(spec)
    net.start()
    add_ipv6(net, spec)
    CLI(net)
    net.stop()
