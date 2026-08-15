#!/usr/bin/env python3
"""End-to-end test: bootstrap, switch death, reconvergence, recovery.

The unit tests in Tests.py cover the routing math on a static topology. This
covers the part that actually broke in practice -- real processes, real UDP,
real timeouts -- and asserts against the graded log format.

Cross-platform: no pkill, no shell globs, no POSIX-only signals.

Run: python integration_test.py
"""

import os
import socket
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "Config", "graph_3.txt")
BOOTSTRAP_TIMEOUT = 20.0
FAILURE_TIMEOUT = 25.0


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def spawn(workdir, script, *args):
    return subprocess.Popen(
        [sys.executable, os.path.join(HERE, script), *[str(a) for a in args]],
        cwd=workdir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )


def read_log(workdir, name):
    path = os.path.join(workdir, name)
    if not os.path.exists(path):
        return ""
    with open(path) as handle:
        return handle.read()


def wait_for(workdir, name, needle, timeout, procs):
    """Poll a log for `needle`, failing fast if a process has already died."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if needle in read_log(workdir, name):
            return True
        for label, proc in procs:
            if proc.poll() is not None:
                raise AssertionError(
                    f"{label} exited with code {proc.returncode} "
                    f"while waiting for {needle!r} in {name}"
                )
        time.sleep(0.25)
    return False


def last_routing_block(text):
    """The final `Routing Update ... Routing Complete` block, as a list."""
    blocks, current = [], None
    for line in text.splitlines():
        line = line.strip()
        if line == "Routing Update":
            current = []
        elif line == "Routing Complete" and current is not None:
            blocks.append(current)
            current = None
        elif current is not None and line:
            current.append(line)
    return blocks[-1] if blocks else []


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail and not condition else ""))
    return condition


def main():
    port = free_port()
    workdir = tempfile.mkdtemp(prefix="sdn-it-")
    print(f"workdir={workdir} port={port}")
    procs = []
    failures = []

    try:
        controller = spawn(workdir, "controller.py", port, CONFIG)
        procs.append(("controller", controller))
        time.sleep(1.0)

        switches = {}
        for i in range(3):
            switches[i] = spawn(workdir, "switch.py", i, "127.0.0.1", port)
            procs.append((f"switch{i}", switches[i]))
            time.sleep(0.2)

        # -- 1. bootstrap --------------------------------------------------
        print("\n1. bootstrap")
        ok = wait_for(workdir, "Controller.log", "Routing Complete",
                      BOOTSTRAP_TIMEOUT, procs)
        if not check("controller converged", ok):
            failures.append("bootstrap")
        else:
            table = last_routing_block(read_log(workdir, "Controller.log"))
            expected = [
                "0,0:0,0", "0,1:1,20", "0,2:2,10",
                "1,0:0,20", "1,1:1,0", "1,2:2,30",
                "2,0:0,10", "2,1:1,30", "2,2:2,0",
            ]
            if not check("initial table matches sample log", table == expected,
                         f"got {table}"):
                failures.append("initial table")

        for i in range(3):
            log = read_log(workdir, f"switch{i}.log")
            if not check(f"switch{i} logged register request/response",
                         "Register Request Sent" in log
                         and "Register Response received" in log):
                failures.append(f"switch{i} registration")

        # -- 2. switch death -----------------------------------------------
        print("\n2. switch death")
        switches[1].kill()
        switches[1].wait()
        procs = [(label, proc) for label, proc in procs if label != "switch1"]

        ok = wait_for(workdir, "Controller.log", "Switch Dead 1",
                      FAILURE_TIMEOUT, procs)
        if not check("controller logged Switch Dead 1", ok):
            failures.append("death detection")

        ok = wait_for(workdir, "switch0.log", "Neighbor Dead 1",
                      FAILURE_TIMEOUT, procs)
        if not check("switch0 logged Neighbor Dead 1", ok):
            failures.append("neighbour detection")

        time.sleep(1.0)
        table = last_routing_block(read_log(workdir, "Controller.log"))
        expected = [
            "0,0:0,0", "0,1:-1,9999", "0,2:2,10",
            "2,0:0,10", "2,1:-1,9999", "2,2:2,0",
        ]
        if not check("post-failure table matches sample log", table == expected,
                     f"got {table}"):
            failures.append("post-failure table")

        # -- 3. recovery ----------------------------------------------------
        print("\n3. recovery")
        switches[1] = spawn(workdir, "switch.py", 1, "127.0.0.1", port)
        procs.append(("switch1", switches[1]))

        ok = wait_for(workdir, "Controller.log", "Switch Alive 1",
                      FAILURE_TIMEOUT, procs)
        if not check("controller logged Switch Alive 1", ok):
            failures.append("recovery detection")

        time.sleep(1.0)
        table = last_routing_block(read_log(workdir, "Controller.log"))
        if not check("network reconverged to full connectivity",
                     len(table) == 9 and "-1,9999" not in " ".join(table),
                     f"got {table}"):
            failures.append("reconvergence")

    finally:
        for _label, proc in procs:
            if proc.poll() is None:
                proc.kill()
        for _label, proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    print()
    if failures:
        print(f"FAILED: {', '.join(failures)}")
        return 1
    print("All integration checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
