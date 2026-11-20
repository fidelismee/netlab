# Networking labs

Weeks 2–4 remain in their existing files and generated pages under `docs/`. Week 6 adds a data-driven, two-tenant VXLAN data centre, practical namespace/tunnel experiments, regression tests, and a generated [Week 6 page](docs/week6/index.html).

Only the permitted suffix **1945** is used: NN = 45, IPv4 allocation `10.45.0.0/16`, IPv6 allocation `fd00:1945::/32`, and underlay `10.45.0.0/24`. The supplied four starter files were used directly, without redownloading them. The existing untracked `nvim.log` was left untouched.

## Week 6 design and implementation

| Hypervisor | Underlay IP | Studio VNI 145 | Archive VNI 245 |
| --- | --- | --- | --- |
| cedar | 10.45.0.1 | st1 (.10), st4 (.13) | ar1 (.10) |
| maple | 10.45.0.2 | st2 (.11) | ar2 (.11) |
| birch | 10.45.0.3 | st3 (.12) | ar3 (.12) |

Both tenants use **10.45.50.0/24**. Each spans all three hypervisors; every hypervisor hosts both tenants. Studio's fourth VM also exercises local bridging. Addresses are assigned from .10 in YAML order, and MACs encode the VNI and address byte: st2 is `02:00:00:91:00:0b`, ar2 is `02:00:00:f5:00:0b`. These hosts model VMs using namespaces, rather than full guest operating systems.

`tenant_commands()` creates `br<VNI>` and `vxlan<VNI>` on participating hypervisors, binds the VXLAN device to its underlay interface with UDP destination port 4789 and no fixed remote, attaches only that tenant's VM ports, sets MTUs and activates interfaces. It deduplicates peer hypervisors and adds one all-zero-MAC flood entry per other tenant VTEP. It derives addresses and ports through the supplied `plan()` and `vm_ports()` helpers; no individual host commands are hardcoded.

`check_mtu()` returns one diagnostic per incompatible tenant before Mininet is imported or constructed. For IPv4, it requires `tenant_mtu + 50 <= underlay_mtu`. The builder stops if any generated VTEP command fails. CLI cleanup uses `finally`. Moving Mininet imports into the runtime paths also permits local validation and page generation without Mininet installed.

`blackhole.yaml` is the exact initial 1500/1500 design, preserved before selecting a fix. `mtu_a.yaml` uses guest 1450 / underlay 1500; `mtu_b.yaml` and final `overlay.yaml` use guest 1500 / underlay 9000. All other topology data is identical.

## Actual experiments and results

Experiments were executed on 20 November 2026 in disposable privileged containers using the already-installed `firdaussahran/netlab-mininet:1.0` image. Docker used the WSL2 kernel `6.18.58.1-microsoft-standard-WSL2`. Containers had their own network namespaces and no external network attachment. No laptop interfaces or previous coursework networks were reconfigured. Each D5 experiment, and each fix, started from a fresh Mininet topology. The two-tenant topology uses Linux bridges, so an OpenFlow controller or OVS service is unnecessary.

| Experiment | Actual result | Evidence |
| --- | --- | --- |
| Part 1: Mininet namespaces | Two hosts, one Linux bridge, `10.45.0.0/24`; distinct network namespace IDs and shell processes; underlay ping passed | [lab.txt](evidence6/lab.txt) |
| Part 2: manual network | Named namespaces red/blue, br0 and veth pairs; `10.45.9.1` to `.2` received 3/3 replies; FDB learned endpoint MACs; objects removed afterwards | [lab.txt](evidence6/lab.txt) |
| Part 3: IPv4 VXLAN | VNI 100, UDP 4789, overlay `10.45.100.1/24` and `.2/24`; ping passed and tcpdump decoded VXLAN | [lab.txt](evidence6/lab.txt) |
| Part 4: overhead | Underlay 1472-byte payload passed, 1473 failed; overlay MTU 1450: payload 1422 passed, 1423 failed | [lab.txt](evidence6/lab.txt) |
| Part 5: IPv6 VXLAN | `fd00:1945::1/64` and `::2/64`, VNI 106, overlay `10.45.106.1/24` and `.2/24`; ping and IPv6 capture passed; observed MTU 1430; payload 1402 passed, 1403 failed | [lab.txt](evidence6/lab.txt) |
| Part 6: receive MTU 1400 | Small ping passed, 1422 failed; adjacent boundary 1326 passed / 1327 failed; receiver RX drops rose 0 → 26; restoring MTU 1500 restored 1422-byte ping and TCP | [lab.txt](evidence6/lab.txt) |
| Part 7: Docker on laptop | Alpine 3.21.10, eth0 `172.17.0.2/16`, PID 1 shell plus sleep/ps; temporary container removal verified | [docker.txt](evidence6/docker.txt) |
| D4 validation | Both faulty tenants rejected, each 50 bytes too large; no network constructed | [check.txt](evidence6/check.txt) |
| D5 A: flood and learn | Third hypervisor birch saw one initial studio ARP broadcast in VNI 145; learned source mapping appeared; repeated successful ping produced zero packets at birch | [flood.txt](evidence6/flood.txt) |
| D5 B: isolation | Successful studio ping with zero ARP/ICMP packets at ar2, then successful archive ping with zero packets at st2; all 18 directed within-tenant pairs passed, including local pair | [isolation.txt](evidence6/isolation.txt) |
| D5 C: forced faulty design | Small ping passed, payload 1422 passed / 1423 failed, TCP receiver throughput zero | [blackhole.txt](evidence6/blackhole.txt) |
| D5 D: Fix A | Payload 1422 passed / 1423 failed locally; throughput measured | [fixes.txt](evidence6/fixes.txt) |
| D5 D: Fix B | Payload 1472 passed / 1473 failed locally; throughput measured | [fixes.txt](evidence6/fixes.txt) |

Actual receiver rates from three-second iperf3 tests (decimal Mbit/s):

| Test | Receiver Mbit/s |
| --- | ---: |
| Part 4 underlay IPv4 | 2705.427 |
| Part 4 IPv4 VXLAN | 1837.956 |
| Part 6 receiving underlay MTU 1400 | 0.000 |
| Part 6 restored MTU 1500 | 1840.496 |
| D5 forced faulty design | 0.000 |
| D5 Fix A | 1373.679 |
| D5 Fix B | 1443.209 |

These are genuine single software-emulation samples, not physical link capacity or repeated performance benchmarks. CPU scheduling, virtual forwarding, disabled VM segmentation offload, and other host activity affect the rates. Mininet warned that it could not raise resource limits and that bridge-netfilter sysctls were enabled. Connectivity tests passed despite those warnings. A tcpdump transmit-side “bad udp cksum” annotation can occur before checksum offload completes; successful decapsulation and pings show it was not evidence of a broken tunnel.

An initial forced run exposed Linux's refusal to set VXLAN MTU 1500 over a bound 1500 underlay; the command failed with `RTNETLINK answers: Invalid argument`, leaving the tunnel down. That genuine failed attempt is retained in [debugging.txt](evidence6/debugging.txt). The corrected builder sets the tunnel MTU to `min(tenant_mtu, underlay_mtu - 50)`. Valid designs receive their requested tenant MTU. In forced mode, only the tunnel is capped at its legal 1450 limit: the YAML, guests and VM links retain the deliberately faulty 1500 plan. Small frames then work, while oversized guest frames disappear at the bridge-to-tunnel boundary. This is a guest MTU black hole, rather than a claim that Linux emitted unsupported 1550-byte packets on a 1500-byte link. [environment.txt](evidence6/environment.txt) also records successful execution of both documented CLI commands, including `--force`.

## Five Week 6 wrap-up answers

No separate Week 6 handout or its verbatim five wrap-up questions was present. The five answers below cover the requested lab topics; all five assignment questions supplied in `page6.yaml` are also answered. Exact alignment with any additional handout remains unverified.

### 1. How do Mininet hosts relate to Linux namespaces and veth pairs?

Mininet starts a shell process in each host's network namespace. Processes launched through that shell use that namespace's interfaces, routes and neighbours, while sharing the container's filesystem and kernel. `lsns` showed h1's shell PID 60 in `net:[4026532609]` and h2's PID 62 in `net:[4026532710]`, distinct from the switch/container namespace. These are IDs from this run and will change on reproduction. The veth peer index connected `h1-eth0@if7` to `s1-eth1@if2` and `h2-eth0@if8` to `s1-eth2@if2`; each host has its own local interface index 2 in its separate namespace.

The manually built red/blue network uses the same primitives explicitly. Each namespace has one end of a veth pair; the other ends, redlink and bluelink, are bridge ports on br0. The bridge learns source MAC addresses, then forwards known unicast to the correct port. Its FDB output and the successful three-packet ping demonstrate that no IP router is needed for communication within `10.45.9.0/24`.

### 2. What does VXLAN encapsulate, and how does it compare with the Week 5 P4 tunnel?

VXLAN transports a tenant Ethernet frame inside VXLAN/UDP/IP. Underlay addresses identify VTEPs; overlay addresses identify tenant endpoints. Here `10.45.0.1` and `.2` transport frames between `10.45.100.1` and `.2` in the basic lab, while assignment VNIs 145 and 245 distinguish identical tenant prefixes. Underlay devices forward the outer packet and do not need to parse the VNI. Only the VTEPs encapsulate, decapsulate and select the tenant bridge. The lab switch itself is an ordinary Linux Ethernet bridge.

The repository and inspected history contain Week 2–4 work and the Week 6 starters, but no Week 5 program, runtime rules or `vtep.p4`. The actual Week 5 overhead and loop-prevention implementation therefore cannot be established. For an explicitly external comparison, the [P4.org tutorial](https://github.com/p4lang/tutorials/blob/master/exercises/basic_tunnel/README.md) defines a four-byte `myTunnel` header containing 16-bit `proto_id` and `dst_id`. That reference adds four bytes after Ethernet, and transit P4 switches understand its custom header and forward using programmed tunnel-ID entries. It is not evidence that the unavailable Week 5 implementation used that format. VXLAN's IPv4 tunnel needs 50 additional bytes relative to the inner IP MTU and works through ordinary IP infrastructure, as specified in [RFC 7348](https://www.rfc-editor.org/rfc/rfc7348.html).

Loop prevention also needs careful scope. This lab has a loop-free underlay star and one VXLAN bridge port per tenant on each hypervisor. Default bridge hairpin behavior prevents sending a frame received from that VXLAN port back out the same port to other VTEPs. Outer IP TTL limits routed underlay loops; it does not repair arbitrary inner Ethernet loops. A custom P4 tunnel needs intentionally correct forwarding rules and, if required, a programmed hop limit or other loop safeguards. The four-byte reference header has no independent TTL. The real Week 5 program must be inspected before attributing any such behavior to it.

### 3. Why are the IPv4 and IPv6 tunnel MTUs different?

The IPv4 overhead relative to the tenant IP packet is `14 inner Ethernet + 8 VXLAN + 8 UDP + 20 outer IPv4 = 50` bytes. Underlay IP MTU 1500 therefore supports guest IP MTU 1450. Outer Ethernet, FCS and preamble are not included in either IP MTU. A normal IPv4 ping adds 20 IP and 8 ICMP bytes, so payload 1422 fills MTU 1450 and 1423 exceeds it. `-M do` prevents the sender from hiding the boundary through fragmentation.

IPv6 replaces the outer 20-byte IPv4 header with a 40-byte IPv6 header, giving 70 bytes of overhead before extension headers. The measured tunnel MTU was 1430, and overlay IPv4 ping payloads 1402 and 1403 straddled its limit. The IPv6 underlay ping and captured IPv6/UDP/VXLAN packets confirm that the second tunnel used the stated IPv6 endpoints rather than silently reusing IPv4.

### 4. Why do small pings work through an MTU black hole while large packets and TCP fail?

Small packets fit the narrowest path even when the endpoints advertise a larger MTU. A receiving underlay MTU of 1400 theoretically leaves `1400 - 50 - 28 = 1322` bytes for an IPv4 ICMP payload. This Linux veth run actually passed 1326 and failed 1327. The four-byte difference is consistent with receive-path allowance for a VLAN-sized addition; it is not a portable MTU guarantee or an extra allowance to use in design. Receiver drops rose from 0 to 26, and TCP delivered zero application data because its full-size data segments exceeded the working path. The zero rate is an obtained receiver result, not an assumed timeout. Restoring the receiving interface MTU to 1500 restored a 1422-byte overlay ping and measured 1840.496 Mbit/s.

The assignment's forced 1500/1500 case differs: guests retain MTU 1500 but Linux restricts the bound VXLAN device to 1450, giving the observed 1422/1423 boundary. Oversized bridged guest frames can be silently lost without an effective IP-layer PMTU signal to the guest. Preventive validation is therefore useful even though small pings work. Fix A reduces every guest/access/tunnel MTU to 1450. Fix B increases the entire underlay to 9000, preserving guest 1500. I select B for a managed jumbo-capable data centre because guests keep their standard MTU; every fabric link must support it. A is the practical fallback on a fixed 1500 transport. The one throughput sample per fix does not prove that B is consistently faster.

### 5. How is a Docker container different from a Mininet host?

Both use kernel isolation rather than a separate hardware virtual machine. A default Mininet host primarily isolates networking: its shell shares the lab filesystem and PID view. A Docker container adds an image-backed root filesystem and normally PID, mount, UTS and other namespaces plus cgroup resource controls. It still shares the Docker engine's Linux kernel. Docker Desktop runs that engine in a Linux VM/WSL environment, so the Alpine kernel is not a separate Alpine kernel.

The laptop-side Alpine run showed eth0 at `172.17.0.2/16`, Alpine 3.21.10 in `/etc/os-release`, and a PID-1 shell with its sleep and ps children. Docker attached its veth to its managed default bridge and normally provides host-mediated external connectivity. Mininet instead lets the lab define each veth and topology explicitly. `--rm` removed the Alpine container after exit; the subsequent Docker container listing was empty for that exact name. Alpine's BusyBox `ip` did not support `-br` in the first attempt, so the verified run used `ip link` and `ip addr`, with both actual attempts retained.

## Reproduce the work

Run from this repository root. Docker commands below are **laptop-host commands**. Only use the disposable course container for privileged network changes. These commands overwrite Week 6 transcripts with new actual measurements; review and regenerate the answers if rates or boundaries change.

```bash
# Host-side Alpine exercise (outside the course container):
python3 week6/run_host.py

# Course lab Parts 1–6:
docker run --rm --privileged --network none \
  -v "$PWD:/work" -w /work --entrypoint python3 \
  firdaussahran/netlab-mininet:1.0 week6/run_lab.py

# D5: a fresh topology for each experiment and for each fix:
docker run --rm --privileged --network none \
  -v "$PWD:/work" -w /work --entrypoint python3 \
  firdaussahran/netlab-mininet:1.0 week6/run_assignment.py all
```

To repeat only one experiment, replace `all` with `flood`, `isolation`, `blackhole` or `fixes`. The blackhole job invokes the same `problems_for(spec, force=True)` path as the documented CLI `--force` option. Capture output includes exit statuses; unexpected expected-success pings stop the runner. iperf3 is bounded to avoid indefinite waits. The runner disables guest TSO/GSO through the supplied builder, and stops only the Mininet network it owns. It does not use global `mn -c` or other system-wide cleanup.

Inside a disposable course container, the interactive builder commands are:

```bash
python3 build_overlay.py overlay.yaml
python3 build_overlay.py blackhole.yaml --force
python3 build_overlay.py mtu_a.yaml
python3 build_overlay.py mtu_b.yaml
```

Exit Mininet before building the next topology. For a manual flood check, start fresh, inspect `cedar bridge fdb show`, capture `birch tcpdump -n -e -vv -i birch-eth0 'udp port 4789'`, and send `st1 ping -c 3 10.45.50.11`. Inspect FDBs again. For isolation, capture `ar2 tcpdump -n -e -i ar2-eth0 'arp or icmp'` while st1 pings `.11`, then reverse tenants. Use `st1 ping -M do -s 1422 -c 2 10.45.50.11` and the adjacent payload for A/blackhole; use 1472/1473 for B. The scripts provide the complete commands for namespaces, IPv6, drop counters, binary boundary searches, and receiver throughput. Do not use Mininet `pingall` with these overlapping tenant addresses.

Static checks and page generation need Python 3 and PyYAML; they also work outside the course container:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
python3 -m py_compile build_overlay.py make_page6.py week6/run_assignment.py week6/run_lab.py week6/run_host.py
python3 build_overlay.py blackhole.yaml > evidence6/check.txt 2>&1
# Expected nonzero exit above: two PROBLEM diagnostics; nothing is built.
python3 make_page6.py overlay.yaml
```

[page6.yaml](page6.yaml) answers all five supplied assignment questions, including EVPN and the limitations of the unavailable lecture P4 code. The generator embeds the actual design, commands and D5 evidence in `docs/week6/index.html`. Supporting evidence includes the full lab, Alpine checks, environment, initial debugging attempt and validation logs.

## AI-use declaration

This assignment permits Level 3 Open AI assistance. **OpenAI Codex** assisted with network design, code implementation, debugging, experiment execution in the available course environment, analysis, documentation and page generation. This work is not represented as completed independently without AI assistance. All experimental outputs and throughput values reported here were actually obtained; unavailable Week 5 implementation details and the missing verbatim lab handout are identified explicitly.

## Submission

Configured repository: <https://github.com/fidelismee/netlab>.
Expected Week 6 URL: <https://fidelismee.github.io/netlab/week6/>. Publication status is recorded after pushing and checking the live page; an expected URL alone does not establish publication.
