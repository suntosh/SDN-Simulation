#!/usr/bin/env python3
"""Launch N switches against a running controller.

Fixes on the original:
  * subprocess.run(['switch.py', ...]) had no interpreter and no exec bit ->
    FileNotFoundError on every switch
  * switch count was hard-coded to 6 regardless of the topology
  * `rm *.log` via shell=True; now a glob, and opt-in
  * no way to shut the fleet down; Ctrl-C now terminates every child
"""

import argparse
import glob
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def switch_count(config_path):
    with open(config_path) as handle:
        for line in handle:
            line = line.strip()
            if line:
                return int(line.split()[0])
    raise ValueError(f"{config_path} is empty")


def main():
    parser = argparse.ArgumentParser(description="Start a fleet of switches.")
    parser.add_argument("hostname", help="controller hostname")
    parser.add_argument("port", type=int, help="controller port")
    parser.add_argument("--config", help="topology file; used to infer switch count")
    parser.add_argument("--count", type=int, help="explicit switch count")
    parser.add_argument("--stagger", type=float, default=0.2,
                        help="delay between launches, seconds")
    parser.add_argument("--clean-logs", action="store_true",
                        help="delete switch*.log before starting")
    parser.add_argument("-f", "--fail-link", nargs=2, type=int, metavar=("SWITCH", "NEIGHBOUR"),
                        help="start SWITCH with a simulated dead link to NEIGHBOUR")
    args = parser.parse_args()

    if args.count:
        count = args.count
    elif args.config:
        count = switch_count(args.config)
    else:
        parser.error("pass --count or --config")

    if args.clean_logs:
        for path in glob.glob(os.path.join(HERE, "switch*.log")):
            os.remove(path)

    procs = []
    for i in range(count):
        cmd = [sys.executable, os.path.join(HERE, "switch.py"),
               str(i), args.hostname, str(args.port)]
        if args.fail_link and args.fail_link[0] == i:
            cmd += ["-f", str(args.fail_link[1])]
        print("launching:", " ".join(cmd))
        procs.append(subprocess.Popen(cmd, cwd=HERE))
        time.sleep(args.stagger)

    def shutdown(_signum, _frame):
        for proc in procs:
            proc.terminate()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for proc in procs:
        proc.wait()
    print("all switches exited")


if __name__ == "__main__":
    main()
