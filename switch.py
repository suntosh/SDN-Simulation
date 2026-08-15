#!/usr/bin/env python3
"""SDN Switch (ECE 50863 Lab Project 1).

Rewritten from the original starter-derived implementation. Fixes:
  * argv was indexed before the argument-count check -> IndexError, not usage
  * dead-neighbour detection only ran when a packet arrived, so a switch whose
    neighbours all went silent never detected anything (blocking recvfrom with
    no timeout). The liveness sweep is now on its own timer.
  * keep-alives went to every reachable destination instead of direct
    neighbours, so every switch looked like every other switch's neighbour
  * keep-alive interval (5s) and timeout (3*K = 6s) were inconsistent, causing
    spurious flapping. Both now derive from K.
  * KeepAliveThread died silently on a KeyError when LOCATIONS was not yet
    populated
  * non-daemon infinite threads made the process unkillable with Ctrl-C
  * shared dicts were mutated from two threads with no lock
  * pickle.loads on a UDP socket (remote code execution) replaced with JSON

Usage: python3 switch.py <id> <controller host> <controller port> [-f <neighbour id>]
"""

import json
import os
import socket
import sys
import threading
import time
from datetime import datetime

LOG_FILE = "switch#.log"

K = 2                       # keep-alive period, seconds
TIMEOUT_MULTIPLIER = 3      # neighbour is dead after TIMEOUT_MULTIPLIER * K
BUFFER_SIZE = 65535
SOCKET_TIMEOUT = 0.5        # so the liveness sweep runs without inbound traffic


# --------------------------------------------------------------------------
# Logging (formats are fixed by the grader -- do not reformat)
# --------------------------------------------------------------------------

def _timestamp():
    return str(datetime.time(datetime.now())) + "\n"


def write_to_log(log):
    with open(LOG_FILE, "a+") as log_file:
        log_file.write("\n\n")
        log_file.writelines(log)


def register_request_sent():
    write_to_log([_timestamp(), "Register Request Sent\n"])


def register_response_received():
    write_to_log([_timestamp(), "Register Response received\n"])


def routing_table_update(routing_table):
    log = [_timestamp(), "Routing Update\n"]
    for row in routing_table:
        log.append(f"{row[0]},{row[1]}:{row[2]}\n")
    log.append("Routing Complete\n")
    write_to_log(log)


def neighbor_dead(switch_id):
    write_to_log([_timestamp(), f"Neighbor Dead {switch_id}\n"])


def neighbor_alive(switch_id):
    write_to_log([_timestamp(), f"Neighbor Alive {switch_id}\n"])


# --------------------------------------------------------------------------
# Switch
# --------------------------------------------------------------------------

class Switch:

    def __init__(self, switch_id, controller_host, controller_port, broken_link=None):
        self.id = switch_id
        self.controller = (controller_host, controller_port)
        self.broken_link = broken_link      # -f: pretend this link is down

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(SOCKET_TIMEOUT)

        self.lock = threading.RLock()
        self.routing_table = {}     # dest -> next hop
        self.locations = {}         # switch id -> (addr, port)
        self.neighbours = set()     # configured neighbours, from the controller
        self.last_seen = {}         # neighbour id -> monotonic timestamp
        self.alive = {}             # neighbour id -> bool
        self.registered = False
        self.link_down_reported = False
        self.stop = threading.Event()

    # -- wire helpers -----------------------------------------------------

    def _send(self, target, message):
        try:
            self.sock.sendto(json.dumps(message).encode("utf-8"), tuple(target))
        except OSError as exc:
            print(f"[switch {self.id}] send to {target} failed: {exc}")

    def _tell_controller(self, kind, target_id):
        self._send(self.controller, {
            "type": kind, "reporter": self.id, "target": target_id,
        })

    def register(self):
        self._send(self.controller, {"type": "REGISTER_REQUEST", "id": self.id})
        register_request_sent()

    # -- state updates ----------------------------------------------------

    def _apply_topology(self, message):
        with self.lock:
            for key, value in message.get("locations", {}).items():
                self.locations[int(key)] = value

            incoming = {int(n) for n in message.get("neighbours", [])}
            for neighbour in incoming - self.neighbours:
                # Unknown until proven otherwise; the -f link starts dead.
                self.alive[neighbour] = (neighbour != self.broken_link)
                self.last_seen[neighbour] = time.monotonic()
            self.neighbours = incoming

    def _handle(self, message):
        kind = message.get("type")

        if kind == "REGISTER_RESPONSE":
            if not self.registered:
                self.registered = True
                register_response_received()
            self._apply_topology(message)

        elif kind == "ROUTE_UPDATE":
            self._apply_topology(message)
            routes = message.get("routes", [])
            routing_table_update(routes)
            with self.lock:
                for row in routes:
                    self.routing_table[int(row[1])] = int(row[2])
            # Report the simulated link failure once we have a table to lose.
            if self.broken_link is not None and not self.link_down_reported:
                self.link_down_reported = True
                self._tell_controller("LINK_DOWN", self.broken_link)

        elif kind == "KEEP_ALIVE":
            sender = int(message["id"])
            if sender == self.broken_link:
                return          # -f: the link is "down", ignore its traffic
            with self.lock:
                was_alive = self.alive.get(sender, False)
                self.last_seen[sender] = time.monotonic()
                self.alive[sender] = True
                self.neighbours.add(sender)
            if not was_alive:
                neighbor_alive(sender)
                self._tell_controller("SWITCH_ALIVE", sender)

    def _sweep(self):
        """Time out silent neighbours. Runs on every loop iteration, not only
        when a packet happens to arrive."""
        deadline = TIMEOUT_MULTIPLIER * K
        now = time.monotonic()
        newly_dead = []
        with self.lock:
            for neighbour in list(self.neighbours):
                if neighbour == self.broken_link:
                    continue
                if not self.alive.get(neighbour, False):
                    continue
                if now - self.last_seen.get(neighbour, now) > deadline:
                    self.alive[neighbour] = False
                    newly_dead.append(neighbour)
        for neighbour in newly_dead:
            neighbor_dead(neighbour)
            self._tell_controller("SWITCH_DEAD", neighbour)

    # -- threads ----------------------------------------------------------

    def _keep_alive_loop(self):
        while not self.stop.wait(K):
            with self.lock:
                targets = [
                    (n, self.locations[n])
                    for n in self.neighbours
                    if n != self.broken_link and n in self.locations
                ]
            for _neighbour, location in targets:
                self._send(location, {"type": "KEEP_ALIVE", "id": self.id})

    def run(self):
        self.register()

        keep_alive = threading.Thread(target=self._keep_alive_loop, daemon=True)
        keep_alive.start()

        retry_at = time.monotonic() + 2.0
        while not self.stop.is_set():
            try:
                data, _addr = self.sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                self._sweep()
                if not self.registered and time.monotonic() > retry_at:
                    self.register()     # datagrams get lost; re-arm
                    retry_at = time.monotonic() + 2.0
                continue
            except OSError as exc:
                print(f"[switch {self.id}] recv error: {exc}")
                continue

            try:
                message = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                print(f"[switch {self.id}] dropping malformed datagram")
                continue

            self._handle(message)
            self._sweep()


def main():
    global LOG_FILE

    # Check argument count BEFORE indexing argv.
    if len(sys.argv) < 4:
        print("Usage: python3 switch.py <id> <controller host> <controller port> "
              "[-f <neighbour id>]")
        sys.exit(1)

    switch_id = int(sys.argv[1])
    controller_host = sys.argv[2]
    controller_port = int(sys.argv[3])

    broken_link = None
    if len(sys.argv) >= 6 and sys.argv[4] == "-f":
        broken_link = int(sys.argv[5])

    LOG_FILE = f"switch{switch_id}.log"

    print(f"[switch {switch_id}] pid={os.getpid()} "
          f"controller={controller_host}:{controller_port} "
          f"broken_link={broken_link}")

    switch = Switch(switch_id, controller_host, controller_port, broken_link)
    try:
        switch.run()
    except KeyboardInterrupt:
        switch.stop.set()
        print(f"\n[switch {switch_id}] shutting down")


if __name__ == "__main__":
    main()
