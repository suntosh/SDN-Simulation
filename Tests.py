#!/usr/bin/env python3
"""Unit tests for the routing logic.

The original Tests.py was scratch: dead code after an early `return`, and three
infinite threads started at import time under `__main__`. Replaced with tests
that pin the behaviours that were actually broken.

Run: python3 -m unittest Tests -v
"""

import os
import tempfile
import unittest

from controller import Topology, INFINITY, NO_HOP


def topology_from(text):
    handle = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    handle.write(text)
    handle.close()
    topology = Topology(handle.name)
    os.unlink(handle.name)
    return topology


def as_dict(table):
    return {(row[0], row[1]): (row[2], row[3]) for row in table}


class TestParsing(unittest.TestCase):

    def test_multi_digit_switch_count(self):
        """Original tested len(line) == 1, so 10+ switches crashed."""
        topology = topology_from("12\n0 1 10\n1 2 10\n")
        self.assertEqual(topology.num_switches, 12)
        self.assertEqual(len(topology.edges), 2)

    def test_blank_lines_tolerated(self):
        topology = topology_from("3\n\n0 1 20\n\n0 2 10\n")
        self.assertEqual(len(topology.edges), 2)

    def test_malformed_edge_rejected(self):
        with self.assertRaises(ValueError):
            topology_from("3\n0 1\n")


class TestRouting(unittest.TestCase):

    def setUp(self):
        self.topology = topology_from("3\n0 1 20\n0 2 10\n1 2 30\n")

    def test_matches_sample_log(self):
        self.assertEqual(as_dict(self.topology.routing_table()), {
            (0, 0): (0, 0),   (0, 1): (1, 20),  (0, 2): (2, 10),
            (1, 0): (0, 20),  (1, 1): (1, 0),   (1, 2): (2, 30),
            (2, 0): (0, 10),  (2, 1): (1, 30),  (2, 2): (2, 0),
        })

    def test_dead_switch_matches_sample_log(self):
        """Rows *from* the dead switch vanish; rows *to* it become -1,9999.

        The original derived these from dead edges and emitted `1,2:-1,9999`
        for a switch that no longer exists.
        """
        self.topology.dead_switches.add(1)
        self.assertEqual(as_dict(self.topology.routing_table()), {
            (0, 0): (0, 0),   (0, 1): (NO_HOP, INFINITY), (0, 2): (2, 10),
            (2, 0): (0, 10),  (2, 1): (NO_HOP, INFINITY), (2, 2): (2, 0),
        })

    def test_partition_does_not_crash(self):
        """Original raised IndexError on sorted([])[0]."""
        topology = topology_from("4\n0 1 10\n2 3 10\n")
        table = as_dict(topology.routing_table())
        self.assertEqual(table[(0, 3)], (NO_HOP, INFINITY))
        self.assertEqual(table[(0, 1)], (1, 10))

    def test_distance_is_path_cost_not_first_hop(self):
        """Original wrote the first-hop cost into the distance column."""
        topology = topology_from("3\n0 1 1\n1 2 1\n0 2 50\n")
        table = as_dict(topology.routing_table())
        self.assertEqual(table[(0, 2)], (1, 2))     # via 1, total 2 -- not 1

    def test_link_down_keeps_the_switch(self):
        """LINK_DOWN removes one edge; the original removed the whole node."""
        topology = topology_from("3\n0 1 1\n1 2 1\n0 2 50\n")
        topology.dead_links.add(frozenset((0, 1)))
        table = as_dict(topology.routing_table())
        self.assertEqual(table[(0, 2)], (2, 50))    # forced onto the long link
        self.assertEqual(table[(0, 1)], (2, 51))    # still reachable via 2

    def test_deterministic_tie_break(self):
        """Equal-cost paths must resolve identically on every run."""
        topology = topology_from("4\n0 1 10\n0 2 10\n1 3 10\n2 3 10\n")
        first = topology.routing_table()
        for _ in range(20):
            self.assertEqual(topology.routing_table(), first)
        self.assertEqual(as_dict(first)[(0, 3)], (1, 20))   # lowest next hop


class TestNeighbours(unittest.TestCase):

    def test_neighbours_are_configured_not_derived(self):
        """A direct link is not always the shortest path, so the switch cannot
        infer its neighbour set from next_hop == dest."""
        topology = topology_from("3\n0 1 100\n0 2 1\n1 2 1\n")
        self.assertEqual(topology.neighbours_of(0), [1, 2])
        table = as_dict(topology.routing_table())
        self.assertEqual(table[(0, 1)], (2, 2))     # next hop is not 1


if __name__ == "__main__":
    unittest.main(verbosity=2)
