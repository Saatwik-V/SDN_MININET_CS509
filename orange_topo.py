#!/usr/bin/env python3
r"""
SDN_MININET_ORANGE - Custom Mininet Topology
CS509 - Software Defined Networking

Orange Topology:
  A multi-tier network with:
    - 2 core switches (cs1, cs2)
    - 4 aggregation switches (as1, as2, as3, as4)
    - 8 edge switches (es1..es8)
    - 16 hosts (h1..h16), 2 per edge switch

           cs1 -------- cs2
          /   \        /   \
        as1   as2    as3   as4
        / \   / \    / \   / \
      es1 es2 es3 es4 es5 es6 es7 es8
      |   |   |   |   |   |   |   |
     h1  h3  h5  h7  h9 h11 h13 h15
     h2  h4  h6  h8 h10 h12 h14 h16
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink


class OrangeTopo(Topo):
    """Orange multi-tier SDN topology for CS509."""

    def build(self, bw_core=1000, bw_agg=100, bw_edge=10):
        """
        Build the Orange topology.

        Args:
            bw_core: Bandwidth (Mbps) on core links (default 1000).
            bw_agg:  Bandwidth (Mbps) on aggregation links (default 100).
            bw_edge: Bandwidth (Mbps) on edge/host links (default 10).
        """
        # --- Core switches ---
        cs1 = self.addSwitch('cs1', dpid='0000000000000001')
        cs2 = self.addSwitch('cs2', dpid='0000000000000002')

        # --- Aggregation switches ---
        agg_switches = []
        for i in range(1, 5):
            sw = self.addSwitch(f'as{i}', dpid=f'{0x10 + i:016x}')
            agg_switches.append(sw)

        # --- Edge switches ---
        edge_switches = []
        for i in range(1, 9):
            sw = self.addSwitch(f'es{i}', dpid=f'{0x20 + i:016x}')
            edge_switches.append(sw)

        # --- Hosts (2 per edge switch) ---
        host_idx = 1
        for es in edge_switches:
            for _ in range(2):
                host = self.addHost(
                    f'h{host_idx}',
                    ip=f'10.0.0.{host_idx}/24',
                    mac=f'00:00:00:00:00:{host_idx:02x}',
                )
                self.addLink(host, es,
                             bw=bw_edge, delay='2ms', loss=0)
                host_idx += 1

        # --- Core <-> Aggregation links ---
        # cs1 connects to as1, as2
        self.addLink(cs1, agg_switches[0], bw=bw_core, delay='1ms')
        self.addLink(cs1, agg_switches[1], bw=bw_core, delay='1ms')
        # cs2 connects to as3, as4
        self.addLink(cs2, agg_switches[2], bw=bw_core, delay='1ms')
        self.addLink(cs2, agg_switches[3], bw=bw_core, delay='1ms')
        # Core interconnect
        self.addLink(cs1, cs2, bw=bw_core, delay='1ms')

        # --- Aggregation <-> Edge links ---
        # as1 -> es1, es2
        self.addLink(agg_switches[0], edge_switches[0], bw=bw_agg, delay='1ms')
        self.addLink(agg_switches[0], edge_switches[1], bw=bw_agg, delay='1ms')
        # as2 -> es3, es4
        self.addLink(agg_switches[1], edge_switches[2], bw=bw_agg, delay='1ms')
        self.addLink(agg_switches[1], edge_switches[3], bw=bw_agg, delay='1ms')
        # as3 -> es5, es6
        self.addLink(agg_switches[2], edge_switches[4], bw=bw_agg, delay='1ms')
        self.addLink(agg_switches[2], edge_switches[5], bw=bw_agg, delay='1ms')
        # as4 -> es7, es8
        self.addLink(agg_switches[3], edge_switches[6], bw=bw_agg, delay='1ms')
        self.addLink(agg_switches[3], edge_switches[7], bw=bw_agg, delay='1ms')


def run(controller_ip='127.0.0.1', controller_port=6633):
    """Create and start the Orange network."""
    setLogLevel('info')
    topo = OrangeTopo()
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        controller=RemoteController('c0', ip=controller_ip, port=controller_port),
        link=TCLink,
        autoSetMacs=False,
    )
    net.start()
    info('\n*** Orange topology started.\n')
    info('*** Running connectivity test...\n')
    net.pingAll()
    info('\n*** Launching CLI. Type "exit" to quit.\n')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    run()
