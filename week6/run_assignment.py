#!/usr/bin/env python3
"""Genuine D5 transcripts. Run as root inside a disposable course container.

Each experiment constructs and stops its own network; no global Mininet cleanup.
Usage: python3 week6/run_assignment.py [flood|isolation|blackhole|fixes|all]
"""
import contextlib
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_overlay import build, check_mtu, load, plan, problems_for
from mininet.log import setLogLevel


def command(node, cmd):
    print(f'{node.name}$ {cmd}', flush=True)
    out, err, code = node.pexec(['sh', '-c', cmd])
    print((out + err).rstrip(), flush=True)
    print(f'[exit status {code}]', flush=True)
    return out + err, code


def ping(node, destination, payload=56, expected=None):
    out, code = command(node, f'ping -n -M do -c 2 -i 0.1 -W 1 -s {payload} {destination}')
    if expected is not None and (code == 0) != expected:
        raise AssertionError(f'Unexpected ping result: {node.name} -> {destination}, size {payload}')
    return code == 0


def throughput(source, target, ip):
    print(f'{target.name}$ iperf3 -s -1 -J', flush=True)
    server = target.popen(['iperf3', '-s', '-1', '-J'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        time.sleep(0.3)
        out, code = command(source, f'timeout 15 iperf3 -c {ip} -t 3 -J --connect-timeout 2000')
        if code == 0:
            data = json.loads(out)
            print(f"ACTUAL receiver throughput: {data['end']['sum_received']['bits_per_second'] / 1e6:.3f} Mbit/s", flush=True)
        else:
            print('No successful receiver throughput measurement.', flush=True)
    finally:
        if server.poll() is None:
            server.terminate()
        result, _ = server.communicate(timeout=5)
        print('iperf3 server output:\n' + result.rstrip(), flush=True)


@contextlib.contextmanager
def capture(node, interface, expression):
    cmd = ['timeout', '8', 'tcpdump', '-U', '-l', '-n', '-e', '-vv', '-i', interface, expression]
    print(f'{node.name}$ ' + ' '.join(cmd), flush=True)
    proc = node.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(0.4)
    try:
        yield
    finally:
        # End tcpdump with SIGINT, preserving its packet counters.
        node.pexec(['pkill', '-INT', '-P', str(proc.pid), 'tcpdump'])
        out, _ = proc.communicate(timeout=10)
        print('CAPTURE:\n' + out.rstrip(), flush=True)
        if 'listening on' not in out:
            raise AssertionError('tcpdump did not start')


@contextlib.contextmanager
def network(path, force=False):
    spec = load(path)
    problems = problems_for(spec, force)
    if problems:
        raise ValueError(problems)
    print(f'Fresh network: {path}; force={force}; {datetime.datetime.now(datetime.timezone.utc).isoformat()}', flush=True)
    if force:
        print('WARNING --force: ' + '; '.join(check_mtu(spec)), flush=True)
    net, _ = build(spec)
    try:
        yield net, spec, plan(spec)
    finally:
        net.stop()


def fdb(net, spec):
    for hv in spec['hypervisors']:
        command(net[hv], 'bridge fdb show')


def flood():
    with network('overlay.yaml') as (net, spec, p):
        fdb(net, spec)
        with capture(net['birch'], 'birch-eth0', 'udp port 4789'):
            ping(net['st1'], p['vms']['st2']['ip'], expected=True)
        fdb(net, spec)
        print('Repeat after learning: third VTEP should receive no unicast conversation.', flush=True)
        with capture(net['birch'], 'birch-eth0', 'udp port 4789'):
            ping(net['st1'], p['vms']['st2']['ip'], expected=True)


def isolation():
    with network('overlay.yaml') as (net, spec, p):
        print('ar2 has the same IP as st2; capture on ar2 while studio communicates.', flush=True)
        with capture(net['ar2'], 'ar2-eth0', 'arp or icmp'):
            ping(net['st1'], p['vms']['st2']['ip'], expected=True)
        with capture(net['st2'], 'st2-eth0', 'arp or icmp'):
            ping(net['ar1'], p['vms']['ar2']['ip'], expected=True)
        # All directed pairs, including the same-hypervisor st1/st4 pair.
        count = 0
        for tenant in spec['tenants']:
            for source, _ in tenant['vms']:
                for target, _ in tenant['vms']:
                    if source != target:
                        ping(net[source], p['vms'][target]['ip'], expected=True)
                        count += 1
        print(f'PASS: {count} directed within-tenant VM pairs', flush=True)
        for vm in p['vms']:
            command(net[vm], f'ip -br address; ip link show {vm}-eth0; ip neigh show')
        fdb(net, spec)


def boundary(source, destination, low, high):
    # Search every remaining candidate by bisection, then explicitly verify adjacent endpoints.
    while low + 1 < high:
        mid = (low + high) // 2
        if ping(source, destination, mid):
            low = mid
        else:
            high = mid
    ping(source, destination, low, expected=True)
    ping(source, destination, high, expected=False)
    print(f'OBSERVED largest successful payload={low}; smallest failing payload={high}', flush=True)
    return low, high


def blackhole():
    with network('blackhole.yaml', force=True) as (net, spec, p):
        destination = p['vms']['st2']['ip']
        command(net['cedar'], 'ip -s -s link show vxlan145; ip -s -s link show cedar-eth0')
        command(net['maple'], 'ip -s -s link show maple-eth0; nstat -az')
        ping(net['st1'], destination, 56, expected=True)
        ping(net['st1'], destination, 1472)
        boundary(net['st1'], destination, 56, 1473)
        throughput(net['st1'], net['st2'], destination)
        command(net['cedar'], 'ip -s -s link show vxlan145; ip -s -s link show cedar-eth0')
        command(net['maple'], 'ip -s -s link show maple-eth0; nstat -az')


def fixes():
    for path, good, bad in [('mtu_a.yaml', 1422, 1423), ('mtu_b.yaml', 1472, 1473)]:
        with network(path) as (net, spec, p):
            for hv in spec['hypervisors']:
                command(net[hv], f'ip -br link; ip -d link show vxlan145')
            destination = p['vms']['st2']['ip']
            ping(net['st1'], destination, good, expected=True)
            ping(net['st1'], destination, bad, expected=False)
            throughput(net['st1'], net['st2'], destination)


def main():
    setLogLevel('warning')
    Path('evidence6').mkdir(exist_ok=True)
    jobs = {'flood': flood, 'isolation': isolation, 'blackhole': blackhole, 'fixes': fixes}
    selected = sys.argv[1] if len(sys.argv) > 1 else 'all'
    for name, job in jobs.items():
        if selected in ('all', name):
            with open(f'evidence6/{name}.txt', 'w') as output, contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                job()
            print(f'Wrote evidence6/{name}.txt', flush=True)


if __name__ == '__main__':
    main()
