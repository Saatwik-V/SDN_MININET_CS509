# SDN_MININET_CS509

POX-based SDN mini project for topology change detection.

## Topology Change Detector (POX)

The controller app in [controller/topo_detect.py](controller/topo_detect.py) now implements a POX topology change detector that:
- Monitors switch up/down events.
- Monitors link add/remove events.
- Updates an internal topology map (switches and links) on every event.
- Displays and logs each change.

## Run

1. Start POX with OpenFlow discovery and this module:

```bash
cd pox
./pox.py log.level --INFO openflow.discovery ext.topo_detect
```

2. Start Mininet using the custom topology:

```bash
sudo mn --custom topology/topo.py --topo mytopo --controller remote,ip=127.0.0.1,port=6633 --switch ovsk,protocols=OpenFlow10
```

3. Trigger topology changes from Mininet (for example):

```bash
mininet> link s1 s2 down
mininet> link s1 s2 up
```

You should see switch/link change logs and updated topology map snapshots in the POX console.