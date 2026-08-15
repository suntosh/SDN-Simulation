# SDN Simulation — ECE 50863 Lab Project 1

Python 3.8+, standard library only. No install step.

## Run

**Terminal 1 — controller:**

```bash
python3 controller.py 3999 Config/graph_3.txt
```

**Terminal 2 — switches.** Either launch the fleet:

```bash
python3 SwitchRunner.py 127.0.0.1 3999 --config Config/graph_3.txt --clean-logs
```

or start them individually, one per terminal:

```bash
python3 switch.py 0 127.0.0.1 3999
python3 switch.py 1 127.0.0.1 3999
python3 switch.py 2 127.0.0.1 3999
```

The controller waits until all N switches (N = first line of the config) have
registered, then computes and pushes routing tables.

### Failure injection

Kill a switch process (`Ctrl-C` or `kill <pid>`). Its neighbours time it out
after `3 * K` = 6 seconds, report `SWITCH_DEAD`, and the controller reconverges.
Restart the same switch and it re-registers; the controller logs `Switch Alive`
and reconverges again.

Simulate a single dead **link** rather than a dead switch:

```bash
python3 switch.py 0 127.0.0.1 3999 -f 1     # switch 0 pretends link 0<->1 is down
```

Or via the runner:

```bash
python3 SwitchRunner.py 127.0.0.1 3999 --config Config/graph_3.txt -f 0 1
```

### Tests

```bash
python3 -m unittest Tests -v
```

## Output

`Controller.log`, `switch0.log`, `switch1.log`, … are written to the working
directory in the grader's format. Compare against `SampleLog/`. Logs are
appended, not truncated — delete them between runs (`--clean-logs` handles the
switch logs).

## Tuning

`K` in `switch.py` is the keep-alive period in seconds; the dead-neighbour
timeout is `3 * K`. Both now derive from the same constant.

---

## What was broken

### `controller.py`

| # | Bug | Effect |
|---|-----|--------|
| 1 | `if len(line) == 1` used to detect the switch-count header | Any topology with 10+ switches parsed the header as an edge → `IndexError` |
| 2 | `sorted(paths.values())[0]` with no path between two nodes | `IndexError` and controller death the moment the graph partitions — exactly the case the lab is testing |
| 3 | Distance column took `cost_sheet[first_hop]` | For any multi-hop route the reported shortest distance was the **first-hop cost**, not the path cost |
| 4 | Unreachability derived from dead *edges* (`bad_routes`) | After killing switch 1 the table emitted `1,2:-1,9999` — a row *from* a switch that no longer exists — and omitted `2,1:-1,9999`. Does not match the sample log |
| 5 | `register_response_sent()` defined but never called | No `Register Response` lines in `Controller.log`; graded log is incomplete |
| 6 | `self.dead_links.remove(mn)` on re-registration | `mn` is a leftover loop variable → `NameError` if a switch registers before any death message |
| 7 | `registered += 1` counted datagrams, not distinct switches | A retransmitted or duplicate register request triggered a premature bootstrap |
| 8 | `LINK_DOWN` handled identically to `SWITCH_DEAD` | Removed every edge incident on the node instead of the one failed link. The switch also never sent its own ID, so the controller could not know which link failed |
| 9 | `recursive_graph_pathing` enumerated all simple paths | Factorial blowup; fine at N=6, unusable beyond ~12 |
| 10 | `pickle.loads()` on a UDP socket | Unauthenticated remote code execution |
| 11 | `data.decode('utf-8')` on every inbound datagram | Any binary datagram crashes the controller |
| 12 | `topology_update_link_dead()` called from inside `generate_routing_table()` | Duplicate `Link Dead` lines on every recompute |
| 13 | `shortest_paths = {…}` dict rebuilt inside the inner loop | O(n²) rebuild per pair |

### `switch.py`

| # | Bug | Effect |
|---|-----|--------|
| 14 | `sys.argv[3]` read *before* the `num_args < 4` check | `IndexError` instead of the usage message |
| 15 | Dead-neighbour sweep ran only inside `process_data()`, behind a blocking `recvfrom()` with no timeout | **The core failure-detection bug.** If every neighbour goes silent, no packet arrives, so the sweep never runs and the death is never detected. Now on a `0.5s` socket timeout |
| 16 | Keep-alives sent to every entry in `ROUTING_TABLE` | Keep-alives went to all reachable switches, not direct neighbours, so every switch appeared to be every other switch's neighbour → wrong `Neighbor Dead` logs |
| 17 | Neighbour set inferred from the routing table | A direct link is not always the shortest path (0–1 cost 100, 0–2–1 cost 2), so real neighbours were missed. The controller now sends the configured neighbour list explicitly |
| 18 | `KeepAliveThread(5)` vs timeout `K * 3` = 6 | 1-second margin between keep-alive and timeout → spurious flapping. Both now derive from `K` |
| 19 | `LOCATIONS[k]` before the locations message arrived | `KeyError` killed the keep-alive thread silently; the switch then looked dead to everyone forever |
| 20 | Non-daemon threads + `while True` + `t.join()` | Process could not be shut down with `Ctrl-C` |
| 21 | `NEIGHBOUR_SWITCH_STATUS` / `ROUTING_TABLE` mutated from two threads, no lock | Torn reads under load |
| 22 | Register response identified as "first packet received" | Any reordering misclassifies it. Messages are now typed |
| 23 | `switch_changes_propagation` held only the last change | Two neighbours dying in the same pass → only one reported |

### `SwitchRunner.py`

| # | Bug | Effect |
|---|-----|--------|
| 24 | `subprocess.run(['switch.py', …])` — no interpreter, no exec bit | `FileNotFoundError` on every switch. The runner never worked |
| 25 | `range(6)` hard-coded | Broke on any topology that isn't graph_6 |
| 26 | `subprocess.run(['rm *.log'], shell=True)` | Shell injection surface; now a glob, and opt-in via `--clean-logs` |
| 27 | No shutdown path | Children survived the parent |

### Other

- `Tests.py` was scratch — dead code after an early `return`, and three infinite
  threads started at import time under `__main__`. Replaced with real unit tests
  covering every routing bug above.
- `1` — a stray git commit message committed as a file. Deleted.
- `graph_6.txt` was duplicated at the repo root and in `Config/`. Root copy deleted.
- Stale `*.log` files from a previous run were committed. Deleted.

## Design changes

**Dijkstra with a deterministic tie-break.** The priority key is
`(cost, hops, next_hop)`, so equal-cost paths resolve identically on every run:
cheapest, then fewest hops, then lowest next-hop ID. The original's
`sorted(paths, key=len)[0]` sorted *string* lengths of path representations,
which is neither hop-count nor stable.

**JSON wire format, uniformly.** The original mixed plaintext (registration) and
pickle (route updates, keep-alives) on the same socket, so a decode had to guess
the format and got it wrong on any out-of-order datagram. Every message is now a
typed JSON object. This also removes the `pickle.loads`-on-a-socket RCE.

**Failure model split into two sets.** `dead_switches` (whole node gone) and
`dead_links` (one edge gone, both endpoints alive) are tracked separately, and
the routing table is computed from a filtered adjacency view rather than by
patching a table after the fact.

## Known limitation

The switch's simulated link failure (`-f`) is one-directional at the reporting
end: switch 0 started with `-f 1` stops sending to and ignores traffic from
switch 1, but switch 1 keeps sending until its own timeout fires. The controller
treats the link as bidirectionally down on the first report, which is correct
for the lab, but switch 1 will log `Neighbor Dead 0` a few seconds later.
