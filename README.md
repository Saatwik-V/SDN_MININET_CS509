# SDN_MININET_CS509 — Orange Simulation

A multi-tier Software-Defined Networking (SDN) simulation built with
[Mininet](http://mininet.org/) and the [RYU](https://ryu-sdn.org/) OpenFlow
controller framework.  This project was developed for **CS509**.

---

## Repository layout

| File | Description |
|------|-------------|
| `orange_topo.py` | Custom Mininet topology (2 core / 4 aggregation / 8 edge switches, 16 hosts) |
| `orange_controller.py` | RYU OpenFlow 1.3 L2 learning-switch controller |
| `firewall_controller.py` | RYU controller with stateless ACL firewall rules |
| `run.sh` | Convenience script that starts RYU and Mininet together |
| `test_topology.py` | Unit tests for the topology (no live Mininet needed) |

---

## Network topology

```
           cs1 -------- cs2
          /   \        /   \
        as1   as2    as3   as4
        / \   / \    / \   / \
      es1 es2 es3 es4 es5 es6 es7 es8
      |   |   |   |   |   |   |   |
     h1  h3  h5  h7  h9 h11 h13 h15
     h2  h4  h6  h8 h10 h12 h14 h16
```

* **Core switches** (`cs1`, `cs2`) — 1 Gbps links, 1 ms delay
* **Aggregation switches** (`as1`–`as4`) — 100 Mbps links, 1 ms delay
* **Edge switches** (`es1`–`es8`) — 10 Mbps links to hosts, 2 ms delay
* **Hosts** (`h1`–`h16`) — IPs `10.0.0.1/24`–`10.0.0.16/24`

---

## Requirements

```bash
sudo apt-get update
sudo apt-get install -y mininet
pip install ryu
```

Python ≥ 3.8 is required.

---

## Running the simulation

### Quick start (L2 learning switch)

```bash
chmod +x run.sh
./run.sh           # same as: ./run.sh learning
```

### With the firewall controller

```bash
./run.sh firewall
```

The script:
1. Starts the RYU controller on TCP port 6633.
2. Launches the Mininet topology connected to that controller.
3. Drops you into the Mininet CLI (`mininet>`) where you can run commands
   such as `pingall`, `iperf h1 h16`, etc.
4. Stops RYU automatically when you type `exit`.

### Manual start

```bash
# Terminal 1 — controller
ryu-manager orange_controller.py --ofp-tcp-listen-port 6633 --verbose

# Terminal 2 — topology (needs root)
sudo python3 orange_topo.py
```

---

## Firewall rules

`firewall_controller.py` installs the following **drop** rules on every
switch at startup (priority 100, above unicast forwarding rules):

| # | Match | Action |
|---|-------|--------|
| 1 | IPv4, src=`10.0.0.1` → dst=`10.0.0.16` | Drop |
| 2 | IPv4, TCP dst-port 23 (Telnet) | Drop |

Edit the `FIREWALL_RULES` list in `firewall_controller.py` to add or remove
rules.

---

## Running the tests

No Mininet installation is needed to run the unit tests:

```bash
pip install pytest
python3 -m pytest test_topology.py -v
```

All 16 tests validate the node counts, naming, IP/MAC assignments, link
structure, and bandwidth parameters of `OrangeTopo`.