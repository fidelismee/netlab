#!/usr/bin/env python3
"""Part 7: run from the laptop, outside the Mininet course container."""
import datetime
from pathlib import Path
import shlex
import subprocess


def main():
    Path('evidence6').mkdir(exist_ok=True)
    with open('evidence6/docker.txt', 'a') as out:
        out.write('\nVerified Part 7 run: ' + datetime.datetime.now(datetime.timezone.utc).isoformat() + '\n')
        commands = [
            ['docker', 'version'],
            ['docker', 'run', '--rm', '--name', 'netlab-week6-alpine', 'alpine:3.21', 'sh', '-c',
             'set -ex; ip link; ip addr; cat /etc/os-release; sleep 1 & ps; wait'],
            ['docker', 'ps', '-a', '--filter', 'name=^/netlab-week6-alpine$', '--format', '{{.Names}}'],
        ]
        for args in commands:
            out.write('$ ' + shlex.join(args) + '\n')
            out.flush()
            result = subprocess.run(args, stdout=out, stderr=subprocess.STDOUT)
            out.write(f'[exit status {result.returncode}]\n')
            if result.returncode:
                raise RuntimeError(shlex.join(args))
    print('Appended verified Alpine run and removal check to evidence6/docker.txt')


if __name__ == '__main__':
    main()
