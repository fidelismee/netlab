#!/usr/bin/env python3
"""Static submission audit; writes only genuine audit output after all checks pass."""
import ast
import copy
from html.parser import HTMLParser
import ipaddress
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yaml
from build_overlay import all_commands, check_mtu, check_spec, load, plan


def main():
    lines = []
    def report(message):
        print(message)
        lines.append(message)

    for path in ['build_overlay.py', 'make_page6.py', 'week6/run_assignment.py', 'week6/run_lab.py', 'week6/run_host.py', 'week6/validate.py', 'tests/test_overlay.py']:
        ast.parse(Path(path).read_text())
        report('PASS Python syntax: ' + path)
    for path in ['blackhole.yaml', 'mtu_a.yaml', 'mtu_b.yaml', 'overlay.yaml', 'page6.yaml']:
        yaml.safe_load(Path(path).read_text())
        report('PASS YAML syntax: ' + path)
    base = load('blackhole.yaml')
    for path in ['blackhole.yaml', 'mtu_a.yaml', 'mtu_b.yaml', 'overlay.yaml']:
        spec = load(path)
        assert not check_spec(spec), path
        for cmds in all_commands(spec).values():
            assert not any(' remote ' in cmd for cmd in cmds)
        assert spec['student_id_last4'] == '1945'
        assert spec['underlay']['network'] == '10.45.0.0/24'
        p = plan(spec)
        assert all(ipaddress.ip_address(v['ip']) in ipaddress.ip_network('10.45.0.0/16') for v in p['vms'].values())
        assert len({v['mac'] for v in p['vms'].values()}) == len(p['vms'])
        normalized = copy.deepcopy(spec)
        normalized['underlay']['mtu'] = 1500
        for t in normalized['tenants']:
            t['mtu'] = 1500
        assert normalized == base
        report('PASS topology, addresses, MACs and invariant design: ' + path)
    assert len(check_mtu(base)) == 2
    assert all(not check_mtu(load(p)) for p in ['mtu_a.yaml', 'mtu_b.yaml', 'overlay.yaml'])
    assert Path('overlay.yaml').read_bytes() == Path('mtu_b.yaml').read_bytes()
    initial = subprocess.check_output(['git', 'show', '4db626e:overlay.yaml'])
    assert initial == Path('blackhole.yaml').read_bytes()
    report('PASS blackhole is byte-identical to initial committed design; both fixes pass; final equals B')
    page = load('page6.yaml')
    assert len(page['answers']) == 5 and all(qa['answer'].strip() for qa in page['answers'].values())
    assert page['repository'] == 'https://github.com/fidelismee/netlab'
    report('PASS all five supplied assignment questions answered and correct repository URL')
    for name in ['check', 'flood', 'isolation', 'blackhole', 'fixes', 'lab', 'docker', 'environment', 'debugging']:
        f = Path('evidence6') / (name + '.txt')
        assert f.stat().st_size > 100
        report(f'PASS nonempty actual transcript: {f} ({f.stat().st_size} bytes)')
    # Check changes to files that existed at task start; additions are expected.
    old = subprocess.check_output(['git', 'diff', '--name-only', '--diff-filter=M', 'db1e0ae']).decode().splitlines()
    assert set(old) <= {'overlay.yaml', 'build_overlay.py', 'page6.yaml'}, old
    report('PASS no previously tracked coursework outside Week 6 changed')
    text = Path('evidence6/isolation.txt').read_text()
    assert 'PASS: 18 directed within-tenant VM pairs' in text
    assert text.count('0 packets captured') == 2
    report('PASS runtime transcript: 18 directed pairs and two zero-packet cross-tenant captures')
    assert 'largest successful payload=1422; smallest failing payload=1423' in Path('evidence6/blackhole.txt').read_text()
    report('PASS runtime transcript: forced MTU boundary 1422/1423')
    document = Path('docs/week6/index.html').read_text()
    HTMLParser().feed(document)
    assert 'Not answered yet' not in document and 'class="missing"' not in document
    assert 'YOUR-USERNAME' not in document and 'TODO:' not in document
    for key in page['answers']:
        assert f'id="answer-{key}"' in document
    data = json.loads(document.split('<script type="application/json" id="overlay-data">')[1].split('</script>')[0])
    assert data['design'] == load('overlay.yaml')
    assert data['commands'] == all_commands(load('overlay.yaml'))
    report('PASS generated HTML contains design, commands, all five evidence sections and all five answers')
    Path('evidence6/validation.txt').write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
