# Week 4: Control Plane Separation and OpenFlow

## Objective

This lab studies the separation between the data plane and the control plane. It uses Open vSwitch flow rules to turn one switch into a hub, a manually configured switch, and a simple firewall. It then connects a controller, observes reactive forwarding, tests controller failure, and compares secure and standalone fail modes.

## Topology and addressing

The required topology is one Open vSwitch (`s1`) and three directly connected hosts, with no controller initially:

```text
         Controller
          (Step 4)
             |
            s1
        /    |    \
       h1    h2    h3
       |     |     |
     Port 1 Port 2 Port 3
```

| Host | IPv4 address | Deterministic MAC | Switch port |
| --- | --- | --- | --- |
| h1 | `10.45.0.1/16` | `00:00:00:00:00:01` | 1 |
| h2 | `10.45.0.2/16` | `00:00:00:00:00:02` | 2 |
| h3 | `10.45.0.3/16` | `00:00:00:00:00:03` | 3 |

The address block is `10.45.0.0/16`, derived from `NN = 45`. The course-wide IPv6 block is `fd00:1945::/32`, although this OpenFlow exercise configures only the stated IPv4 host addresses.

The required launch command is:

```bash
sudo mn --topo single,3 --mac --switch ovs,datapath=user \
  --controller none --ipbase 10.45.0.0/16
```

## Evidence status

All Steps 0–6 were executed on 5 November 2026 in the existing `firdaussahran/netlab-mininet:1.0` course image. The local WSL environments did not contain Mininet and Docker Desktop was initially stopped. After Docker was started and its backend recovered from one HTTP 500 failure, the image provided Mininet and Open vSwitch 3.3.9. Its service script could not load an Open vSwitch kernel module, so `ovs-vswitchd` was started explicitly and the required user-space (`netdev`) datapath was used. The complete environment history is in [`evidence/environment.txt`](evidence/environment.txt).

[`run_lab.py`](run_lab.py) executed the experiments sequentially through the Mininet API, and [`collect.cli`](collect.cli) remains an interactive checklist. The evidence files contain selected genuine command output from the run. Two deviations are reported as observed: one cached packet escaped immediately after the high-priority firewall rule was installed, and the controller database still displayed a stale `is_connected: true` one second after the controller process ended.

## Experiments

### Step 0 — Empty switch

The flow dump contained no entries. The h1-to-h2 ping sent two packets, received none, and reported 100% loss because the data plane had no forwarding instruction. See [`evidence/step0-empty.txt`](evidence/step0-empty.txt).

### Step 1 — Hub

After `actions=flood` was installed, `pingall` reported 0% loss. The rule counter rose from 5 to 27 packets. h3 captured all three h1-to-h2 echo requests and all three replies, demonstrating hub behavior and loss of traffic isolation. See [`evidence/step1-hub.txt`](evidence/step1-hub.txt).

### Step 2 — Manual forwarding

The hub rule was removed, ARP flooding was retained, and the three destination-MAC rules were installed. `pingall` again reported 0% loss. During a successful three-packet h1-to-h2 ping, h3 captured zero ICMP packets. See [`evidence/step2-manual.txt`](evidence/step2-manual.txt).

### Step 3 — Firewall and priority

The default-priority drop had no effect: h1-to-h3 received all three replies and its drop counter remained zero. After priority 40000 was used, h1-to-h2 still received all three replies and h3-to-h1 received none. The first h1-to-h3 reply escaped, after which two requests and the three reverse-direction replies were dropped; the drop counter reached six. This is the observed datapath-caching exception anticipated by the lab instructions, so the h1-to-h3 test had 66.7% rather than 100% loss. See [`evidence/step3-firewall.txt`](evidence/step3-firewall.txt).

### Step 4 — Connect the controller

The controller was configured at `tcp:127.0.0.1:6653` in secure mode. Both tested conversations received all three replies. The flow table contained the priority-0 `CONTROLLER:128` table-miss entry and priority-1 reactive ICMP entries with 60-second idle timeouts. This `ovs-vsctl show` version did not print an `is_connected` line, but the successful reactive installation proves that the controller was connected. See [`evidence/step4-controller.txt`](evidence/step4-controller.txt).

### Step 5 — Controller failure

One second after `ovs-testcontroller` was terminated, `ovs-vsctl list controller` still displayed the stale state `is_connected: true`; this is reported rather than replaced with the expected value. Traffic showed the actual failure state: the existing h1-to-h2 conversation received all three replies, while the new h1-to-h3 conversation received none. After 70 seconds, the priority-1 flows with 60-second idle timeouts had disappeared and h1-to-h2 also failed with 100% loss. Only the priority-0 controller rule remained. See [`evidence/step5-failure.txt`](evidence/step5-failure.txt).

### Step 6 — Secure versus standalone

After the fail mode was changed to standalone and the required 15 seconds elapsed, h1-to-h3 received both replies with 0% loss. The local learning-switch fallback therefore restored connectivity without the controller. See [`evidence/step6-standalone.txt`](evidence/step6-standalone.txt).

## Reflection questions

### 1. Why did the first firewall rule have no effect, and why does blocking h1 to h3 also break h3 to h1?

The manual destination-MAC rule and the first ICMP drop rule both use the default OpenFlow priority. They overlap for ICMP packets sent from h1 to h3. Equal priority does not make the later, more specific-looking rule reliably override the forwarding rule; OpenFlow selection among equal-priority matching rules is not a safe firewall policy. Giving the drop rule priority 40000 makes its decision take precedence over the default-priority forwarding entry.

The high-priority match is directional: source h1 and destination h3. A ping from h3 to h1 sends its echo request in the permitted h3-to-h1 direction, but h1's echo reply has source h1 and destination h3. The reply is therefore dropped, so h3 never completes the ping.

### 2. Why did one conversation survive controller failure and another one did not?

A reactive controller installs forwarding flows after it sees the first packets of a conversation. Those flows reside in the switch data plane, so an already learned h1-to-h2 conversation can continue temporarily after the controller fails. New h1-to-h3 traffic has no matching learned entry. It follows the table-miss path, but the unavailable controller cannot make a decision or install new flows. Existing communication also fails when its learned entries reach their idle or hard timeout and expire.

### 3. Secure or standalone: which would I choose for a campus network, and what does the other choice cost?

I would choose secure mode for a campus network whose access controls depend on the controller. It fails closed: a controller outage may interrupt new connections, but the switches do not silently replace centrally defined policy with ordinary learning-switch behavior. This makes the security state predictable and prevents an outage from bypassing segmentation or firewall rules.

Standalone mode costs policy assurance. It maintains more connectivity by falling back to local MAC learning, which is useful when availability is the overriding requirement, but traffic that the controller would normally restrict may then be forwarded. Secure mode has the opposite cost: stronger centralized policy enforcement in exchange for reduced availability during a controller failure. In practice, a campus should reduce that availability cost with redundant controllers and tested recovery procedures rather than weakening the fail mode.

## Reproduction

Run the lab inside the course container from the repository root. Start the Open vSwitch service and `ovs-vswitchd` first if the container does not do so automatically:

```bash
sudo python3 week4/run_lab.py 2>&1 \
  | tee week4/evidence/mininet-transcript.txt
```

Review the new transcript before replacing the evidence because timing-dependent counters and packet caching can differ between runs.
