#!/usr/bin/env python3
"""
SDN_MININET_ORANGE - Topology Unit Tests
CS509 - Software Defined Networking

Validates the OrangeTopo structure without requiring a live Mininet or
controller process.  Run with:

    python3 -m pytest test_topology.py -v
"""

import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Lightweight stubs so we can import orange_topo.py without a real Mininet
# installation.
# ---------------------------------------------------------------------------

class _FakeTopo:
    """Minimal stand-in for mininet.topo.Topo."""

    def __init__(self):
        self._switches: list[tuple[str, dict]] = []
        self._hosts: list[tuple[str, dict]] = []
        self._links: list[tuple[str, str, dict]] = []

    # Replicate the Topo API used by OrangeTopo.build()
    def addSwitch(self, name, **opts):
        self._switches.append((name, opts))
        return name

    def addHost(self, name, **opts):
        self._hosts.append((name, opts))
        return name

    def addLink(self, node1, node2, **opts):
        self._links.append((node1, node2, opts))

    def build(self, **params):
        pass


def _make_orange_topo(**kwargs):
    """
    Return an OrangeTopo instance backed by the _FakeTopo stubs so that
    no real Mininet import is needed.
    """
    import importlib, sys, types

    # Build stub modules only once
    if 'mininet' not in sys.modules:
        # mininet package stub
        mn_pkg = types.ModuleType('mininet')
        sys.modules['mininet'] = mn_pkg

        topo_mod = types.ModuleType('mininet.topo')
        topo_mod.Topo = _FakeTopo
        sys.modules['mininet.topo'] = topo_mod
        mn_pkg.topo = topo_mod

        for sub in ('net', 'node', 'cli', 'log', 'link'):
            m = types.ModuleType(f'mininet.{sub}')
            # Provide dummy names that OrangeTopo imports
            m.Mininet = MagicMock()
            m.RemoteController = MagicMock()
            m.OVSSwitch = MagicMock()
            m.CLI = MagicMock()
            m.setLogLevel = MagicMock()
            m.info = MagicMock()
            m.TCLink = MagicMock()
            sys.modules[f'mininet.{sub}'] = m
            setattr(mn_pkg, sub, m)

    # Import (or reload) our topology module
    if 'orange_topo' in sys.modules:
        topo_mod = importlib.reload(sys.modules['orange_topo'])
    else:
        import orange_topo as topo_mod

    obj = topo_mod.OrangeTopo()
    obj.build(**kwargs)
    return obj


class TestOrangeTopoNodeCounts(unittest.TestCase):
    """Verify correct number of nodes in the Orange topology."""

    @classmethod
    def setUpClass(cls):
        cls.topo = _make_orange_topo()

    def test_switch_count(self):
        # 2 core + 4 aggregation + 8 edge = 14 switches
        self.assertEqual(len(self.topo._switches), 14)

    def test_host_count(self):
        # 8 edge switches × 2 hosts = 16 hosts
        self.assertEqual(len(self.topo._hosts), 16)

    def test_switch_names(self):
        names = {s[0] for s in self.topo._switches}
        self.assertIn('cs1', names)
        self.assertIn('cs2', names)
        for i in range(1, 5):
            self.assertIn(f'as{i}', names)
        for i in range(1, 9):
            self.assertIn(f'es{i}', names)

    def test_host_names(self):
        names = {h[0] for h in self.topo._hosts}
        for i in range(1, 17):
            self.assertIn(f'h{i}', names)

    def test_host_ips(self):
        for name, opts in self.topo._hosts:
            idx = int(name[1:])  # strip leading 'h'
            self.assertEqual(opts['ip'], f'10.0.0.{idx}/24')

    def test_host_macs(self):
        for name, opts in self.topo._hosts:
            idx = int(name[1:])
            expected_mac = f'00:00:00:00:00:{idx:02x}'
            self.assertEqual(opts['mac'], expected_mac)

    def test_unique_dpids(self):
        dpids = [opts.get('dpid') for _, opts in self.topo._switches]
        # All DPIDs must be unique
        self.assertEqual(len(dpids), len(set(dpids)))


class TestOrangeTopoLinkCounts(unittest.TestCase):
    """Verify link structure of the Orange topology."""

    @classmethod
    def setUpClass(cls):
        cls.topo = _make_orange_topo()

    def _link_set(self):
        return {frozenset([a, b]) for a, b, _ in self.topo._links}

    def test_total_link_count(self):
        # 16 host-edge + 8 edge-agg + 4 agg-core + 1 core-core = 29
        self.assertEqual(len(self.topo._links), 29)

    def test_core_interconnect(self):
        self.assertIn(frozenset(['cs1', 'cs2']), self._link_set())

    def test_core_to_agg_links(self):
        ls = self._link_set()
        self.assertIn(frozenset(['cs1', 'as1']), ls)
        self.assertIn(frozenset(['cs1', 'as2']), ls)
        self.assertIn(frozenset(['cs2', 'as3']), ls)
        self.assertIn(frozenset(['cs2', 'as4']), ls)

    def test_agg_to_edge_links(self):
        ls = self._link_set()
        self.assertIn(frozenset(['as1', 'es1']), ls)
        self.assertIn(frozenset(['as1', 'es2']), ls)
        self.assertIn(frozenset(['as4', 'es7']), ls)
        self.assertIn(frozenset(['as4', 'es8']), ls)

    def test_host_to_edge_links(self):
        ls = self._link_set()
        # h1 and h2 should connect to es1
        self.assertIn(frozenset(['h1', 'es1']), ls)
        self.assertIn(frozenset(['h2', 'es1']), ls)
        # h15 and h16 should connect to es8
        self.assertIn(frozenset(['h15', 'es8']), ls)
        self.assertIn(frozenset(['h16', 'es8']), ls)

    def test_host_links_have_bandwidth(self):
        for a, b, opts in self.topo._links:
            # Every host link should carry a 'bw' parameter
            if a.startswith('h') or b.startswith('h'):
                self.assertIn('bw', opts)

    def test_link_delays_present(self):
        for _, _, opts in self.topo._links:
            self.assertIn('delay', opts)


class TestOrangeTopoCustomBandwidth(unittest.TestCase):
    """Verify that custom bandwidth parameters propagate to links."""

    def test_custom_bw_core(self):
        topo = _make_orange_topo(bw_core=500, bw_agg=50, bw_edge=5)
        # Core interconnect should use bw_core=500
        for a, b, opts in topo._links:
            if frozenset([a, b]) == frozenset(['cs1', 'cs2']):
                self.assertEqual(opts['bw'], 500)

    def test_custom_bw_edge(self):
        topo = _make_orange_topo(bw_core=500, bw_agg=50, bw_edge=5)
        for a, b, opts in topo._links:
            if a.startswith('h') or b.startswith('h'):
                self.assertEqual(opts['bw'], 5)


if __name__ == '__main__':
    unittest.main()
