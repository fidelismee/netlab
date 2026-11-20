"""Regression checks for data-driven VXLAN commands and pre-build MTU rejection."""
import copy
import subprocess
import sys
import unittest
from pathlib import Path

from build_overlay import all_commands, check_mtu, check_spec, load, plan, problems_for, tenant_commands


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.spec = load('overlay.yaml')

    def test_designs_and_exact_mtu_boundary(self):
        for path in ('overlay.yaml', 'blackhole.yaml', 'mtu_a.yaml', 'mtu_b.yaml'):
            self.assertEqual(check_spec(load(path)), [], path)
        for path in ('overlay.yaml', 'mtu_a.yaml', 'mtu_b.yaml'):
            self.assertEqual(check_mtu(load(path)), [], path)
        faulty = load('blackhole.yaml')
        self.assertEqual(len(check_mtu(faulty)), 2)
        self.assertTrue(all('50 bytes' in problem for problem in check_mtu(faulty)))
        self.assertEqual(problems_for(faulty, True), [])
        faulty['tenants'][0]['vni'] = faulty['tenants'][1]['vni']
        self.assertTrue(problems_for(faulty, True))
        spec = load('mtu_a.yaml')
        spec['tenants'][0]['mtu'] += 1
        self.assertEqual(len(check_mtu(spec)), 1)
        self.assertIn('by 1 bytes', check_mtu(spec)[0])

    def test_cli_rejects_before_mininet(self):
        result = subprocess.run([sys.executable, 'build_overlay.py', 'blackhole.yaml'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count('PROBLEM:'), 2)
        self.assertIn('nothing was built', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_addresses_and_mac_uniqueness(self):
        p = plan(self.spec)
        self.assertEqual(p['hypervisors'], {'cedar': '10.45.0.1', 'maple': '10.45.0.2', 'birch': '10.45.0.3'})
        self.assertEqual(p['vms']['st2']['ip'], p['vms']['ar2']['ip'])
        self.assertEqual(len({v['mac'] for v in p['vms'].values()}), len(p['vms']))
        self.assertEqual(p['vms']['st2']['mac'], '02:00:00:91:00:0b')

    def test_ports_peers_and_no_fixed_remote(self):
        commands = all_commands(self.spec)
        for hv, cmds in commands.items():
            for tenant in self.spec['tenants']:
                selected = tenant_commands(self.spec, hv, tenant)
                floods = [c for c in selected if c.startswith('bridge fdb append')]
                self.assertEqual(len(floods), 2)
                self.assertFalse(any(' remote ' in c for c in selected))
            self.assertTrue(cmds)
        cedar = '\n'.join(commands['cedar'])
        self.assertIn('ip link set cedar-eth2 master br145', cedar)  # st4 follows st1
        self.assertIn('ip link set cedar-eth3 master br245', cedar)

    def test_other_valid_design_not_hardcoded(self):
        spec = copy.deepcopy(self.spec)
        spec['hypervisors'] = ['oak', 'pine', 'elm', 'ash']
        spec['tenants'][0].update(vni=16777215, vms=[['a1', 'oak'], ['a2', 'pine'], ['a3', 'elm'], ['a4', 'ash'], ['a5', 'ash']])
        spec['tenants'][1].update(vni=4096, vms=[['b1', 'pine'], ['b2', 'elm']])
        self.assertEqual(check_spec(spec), [])
        self.assertEqual(tenant_commands(spec, 'oak', spec['tenants'][1]), [])
        cmds = tenant_commands(spec, 'ash', spec['tenants'][0])
        self.assertIn('ip link set ash-eth2 master br16777215', cmds)
        self.assertEqual(len([c for c in cmds if c.startswith('bridge fdb append')]), 3)
        self.assertFalse(any('dst 10.45.0.4' in c for c in cmds))

    def test_forced_design_keeps_guest_mismatch_and_legal_tunnel(self):
        spec = load('blackhole.yaml')
        cmds = tenant_commands(spec, 'cedar', spec['tenants'][0])
        self.assertIn('ip link set vxlan145 mtu 1450 up', cmds)
        self.assertIn('ip link set cedar-eth1 mtu 1500 up', cmds)
        self.assertTrue(check_mtu(spec))  # operational small packets do not validate the plan


if __name__ == '__main__':
    unittest.main()
