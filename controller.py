#!/usr/bin/env python3
"""SDN Controller (ECE 50863 Lab Project 1).

Rewritten from the original starter-derived implementation. Fixes:
  * multi-digit switch counts in the config file
  * IndexError when the topology partitions (no path between two nodes)
  * shortest-distance column reported the first-hop cost, not the path cost
  * "Register Response" was never logged
  * unreachable pairs were derived from dead *edges* instead of dead *pairs*
  * NameError on re-registration (stale `mn` variable)
  * registration counter counted messages, not distinct switches
  * exponential all-simple-paths search replaced with Dijkstra
  * pickle-over-UDP replaced with JSON (pickle.loads on a network socket is
    remote code execution)

Usage: python3 controller.py <port> <config file>
"""

import heapq
import json
import os
import socket
import sys
from datetime import datetime

LOG_FILE = "Controller.log"

IP = "0.0.0.0"
BUFFER_SIZE = 65535
INFINITY = 9999
NO_HOP = -1


# --------------------------------------------------------------------------
# Topology
# --------------------------------------------------------------------------

class Topology:
    """Static config topology plus the live failure overlay."""

    def __init__(self, filename):
        self.filename = filename
        self.num_switches = 0
        self.edges = {}                 # frozenset({u, v}) -> cost
        self.dead_switches = set()      # switch ids reported dead
        self.dead_links = set()         # frozenset({u, v}) reported down
        self._load()

    def _load(self):
        with open(self.filename) as handle:
            lines = [ln.strip() for ln in handle if ln.strip()]

        if not lines:
            raise ValueError(f"{self.filename} is empty")

        # First non-blank line is the switch count. Do NOT test len(line) == 1;
        # that silently breaks at 10 switches.
        header = lines[0].split()
        if len(header) != 1:
            raise ValueError(f"{self.filename}: first line must be the switch count")
        self.num_switches = int(header[0])

        for line in lines[1:]:
            parts = line.split()
            if len(parts) != 3:
                raise ValueError(f"{self.filename}: malformed edge line: {line!r}")
            u, v, cost = int(parts[0]), int(parts[1]), int(parts[2])
            self.edges[frozenset((u, v))] = cost

    @property
    def switches(self):
        return list(range(self.num_switches))

    def live_adjacency(self):
        """Adjacency for the current view of the network."""
        adj = {s: {} for s in self.switches if s not in self.dead_switches}
        for link, cost in self.edges.items():
            u, v = tuple(link)
            if u in self.dead_switches or v in self.dead_switches:
                continue
            if link in self.dead_links:
                continue
            if u in adj and v in adj:
                adj[u][v] = cost
                adj[v][u] = cost
        return adj

    def neighbours_of(self, switch_id):
        """Configured neighbours, ignoring failures.

        The switch needs the full configured list so it can notice a neighbour
        coming *back*.
        """
        out = []
        for link in self.edges:
            u, v = tuple(link)
            if u == switch_id:
                out.append(v)
            elif v == switch_id:
                out.append(u)
        return sorted(out)

    # -- routing ----------------------------------------------------------

    def _dijkstra(self, source, adj):
        """Return {dest: (cost, hops, next_hop)} for everything reachable.

        The priority key is (cost, hops, next_hop) so ties resolve
        deterministically: cheapest first, then fewest hops, then lowest
        next-hop id. Without this the routing table is non-deterministic
        across runs and the grader diff is unstable.
        """
        best = {source: (0, 0, source)}
        queue = [(0, 0, source, source)]
        while queue:
            cost, hops, next_hop, node = heapq.heappop(queue)
            if (cost, hops, next_hop) > best.get(node, (INFINITY, 0, NO_HOP)):
                continue
            for neighbour, edge_cost in adj.get(node, {}).items():
                hop = neighbour if node == source else next_hop
                candidate = (cost + edge_cost, hops + 1, hop)
                if candidate < best.get(neighbour, (INFINITY + 1, 0, 0)):
                    best[neighbour] = candidate
                    heapq.heappush(
                        queue, (candidate[0], candidate[1], candidate[2], neighbour)
                    )
        return best

    def routing_table(self):
        """Full table: [[src, dest, next_hop, distance], ...].

        Rows leaving a dead switch are omitted. Rows *toward* an unreachable
        switch are emitted as (-1, 9999). This matches the sample log; the
        original derived these from dead edges and produced rows like
        `1,2:-1,9999` for a switch that no longer exists.
        """
        adj = self.live_adjacency()
        table = []
        for src in self.switches:
            if src in self.dead_switches:
                continue
            best = self._dijkstra(src, adj)
            for dest in self.switches:
                if dest in best:
                    cost, _hops, next_hop = best[dest]
                    table.append([src, dest, next_hop, cost])
                else:
                    table.append([src, dest, NO_HOP, INFINITY])
        return table


# --------------------------------------------------------------------------
# Logging (formats are fixed by the grader -- do not reformat)
# --------------------------------------------------------------------------

def _timestamp():
    return str(datetime.time(datetime.now())) + "\n"


def write_to_log(log):
    with open(LOG_FILE, "a+") as log_file:
        log_file.write("\n\n")
        log_file.writelines(log)


def register_request_received(switch_id):
    write_to_log([_timestamp(), f"Register Request {switch_id}\n"])


def register_response_sent(switch_id):
    write_to_log([_timestamp(), f"Register Response {switch_id}\n"])


def routing_table_update(routing_table):
    log = [_timestamp(), "Routing Update\n"]
    for row in routing_table:
        log.append(f"{row[0]},{row[1]}:{row[2]},{row[3]}\n")
    log.append("Routing Complete\n")
    write_to_log(log)


def topology_update_link_dead(switch_id_1, switch_id_2):
    write_to_log([_timestamp(), f"Link Dead {switch_id_1},{switch_id_2}\n"])


def topology_update_switch_dead(switch_id):
    write_to_log([_timestamp(), f"Switch Dead {switch_id}\n"])


def topology_update_switch_alive(switch_id):
    write_to_log([_timestamp(), f"Switch Alive {switch_id}\n"])


# --------------------------------------------------------------------------
# Controller
# --------------------------------------------------------------------------

class Controller:

    def __init__(self, port, config_file):
        self.port = port
        self.topology = Topology(config_file)
        self.registered = {}    # switch_id -> (addr, port)
        self.sock = None
        self.bootstrapped = False

    # -- wire helpers -----------------------------------------------------

    def _send(self, switch_id, message):
        target = self.registered.get(switch_id)
        if target is None:
            return
        try:
            self.sock.sendto(json.dumps(message).encode("utf-8"), tuple(target))
        except OSError as exc:
            print(f"[controller] send to switch {switch_id} failed: {exc}")

    def _push_routes(self):
        """Recompute and push per-switch routing tables."""
        table = self.topology.routing_table()
        routing_table_update(table)

        for switch_id in self.registered:
            if switch_id in self.topology.dead_switches:
                continue
            rows = [[r[0], r[1], r[2]] for r in table if r[0] == switch_id]
            self._send(switch_id, {
                "type": "ROUTE_UPDATE",
                "routes": rows,
                "neighbours": self.topology.neighbours_of(switch_id),
                "locations": {str(k): v for k, v in self.registered.items()},
            })

    # -- event handlers ---------------------------------------------------

    def _on_register(self, switch_id, client_addr):
        register_request_received(switch_id)
        came_back = (
            switch_id in self.topology.dead_switches
            or (self.bootstrapped and switch_id not in self.registered)
        )
        self.registered[switch_id] = [client_addr[0], client_addr[1]]

        if switch_id in self.topology.dead_switches:
            self.topology.dead_switches.discard(switch_id)
            # A returning switch clears any link failures it was party to.
            self.topology.dead_links = {
                l for l in self.topology.dead_links if switch_id not in l
            }
            topology_update_switch_alive(switch_id)

        self._send(switch_id, {
            "type": "REGISTER_RESPONSE",
            "id": switch_id,
            "neighbours": self.topology.neighbours_of(switch_id),
            "locations": {str(k): v for k, v in self.registered.items()},
        })
        register_response_sent(switch_id)

        if not self.bootstrapped and len(self.registered) >= self.topology.num_switches:
            self.bootstrapped = True
            self._push_routes()
        elif came_back:
            self._push_routes()

    def _on_switch_dead(self, dead_id):
        if dead_id in self.topology.dead_switches:
            return
        self.topology.dead_switches.add(dead_id)
        topology_update_switch_dead(dead_id)
        self._push_routes()

    def _on_switch_alive(self, alive_id):
        if alive_id not in self.topology.dead_switches:
            return
        self.topology.dead_switches.discard(alive_id)
        topology_update_switch_alive(alive_id)
        self._push_routes()

    def _on_link_down(self, reporter, neighbour):
        """A single link failed -- not the whole switch.

        The original treated LINK_DOWN identically to SWITCH_DEAD and removed
        every edge incident on the reported node, which is wrong whenever the
        node still has other working links.
        """
        link = frozenset((reporter, neighbour))
        if link in self.topology.dead_links:
            return
        self.topology.dead_links.add(link)
        topology_update_link_dead(reporter, neighbour)
        self._push_routes()

    # -- main loop --------------------------------------------------------

    def serve(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((IP, self.port))
        print(f"[controller] pid={os.getpid()} listening on {self.sock.getsockname()}")
        print(f"[controller] expecting {self.topology.num_switches} switches")

        handlers = {
            "SWITCH_DEAD": lambda m: self._on_switch_dead(int(m["target"])),
            "SWITCH_ALIVE": lambda m: self._on_switch_alive(int(m["target"])),
            "LINK_DOWN": lambda m: self._on_link_down(
                int(m["reporter"]), int(m["target"])
            ),
        }

        while True:
            try:
                data, client_addr = self.sock.recvfrom(BUFFER_SIZE)
            except OSError as exc:
                print(f"[controller] recv error: {exc}")
                continue

            try:
                message = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                # Never let a malformed datagram take the controller down.
                print(f"[controller] dropping malformed datagram from {client_addr}")
                continue

            kind = message.get("type")
            if kind == "REGISTER_REQUEST":
                self._on_register(int(message["id"]), client_addr)
            elif kind in handlers:
                handlers[kind](message)
            else:
                print(f"[controller] unknown message type {kind!r}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 controller.py <port> <config file>")
        sys.exit(1)

    controller = Controller(int(sys.argv[1]), sys.argv[2])
    print(f"[controller] loaded {sys.argv[2]}: "
          f"{controller.topology.num_switches} switches, "
          f"{len(controller.topology.edges)} links")
    try:
        controller.serve()
    except KeyboardInterrupt:
        print("\n[controller] shutting down")


if __name__ == "__main__":
    main()
