from pox.core import core
from pox.lib.util import dpid_to_str

log = core.getLogger()


class TopologyChangeDetector(object):
    """POX app that monitors switch/link events and maintains a live topology map."""

    def __init__(self):
        self.switches = set()
        self.links = set()

        core.openflow.addListeners(self)
        core.openflow_discovery.addListeners(self)

        log.info("TopologyChangeDetector started and waiting for topology events")

    def _link_tuple(self, link):
        return (
            dpid_to_str(link.dpid1),
            int(link.port1),
            dpid_to_str(link.dpid2),
            int(link.port2),
        )

    def _log_topology_map(self):
        switches = sorted(self.switches)
        links = sorted(self.links)

        log.info("Topology map updated")
        log.info("Switches (%s): %s", len(switches), switches)
        log.info("Links (%s): %s", len(links), links)

    def _handle_ConnectionUp(self, event):
        dpid = dpid_to_str(event.dpid)
        self.switches.add(dpid)
        log.info("Switch added: %s", dpid)
        self._log_topology_map()

    def _handle_ConnectionDown(self, event):
        dpid = dpid_to_str(event.dpid)

        if dpid in self.switches:
            self.switches.remove(dpid)

        stale_links = [
            link
            for link in self.links
            if link[0] == dpid or link[2] == dpid
        ]
        for link in stale_links:
            self.links.remove(link)

        log.info("Switch removed: %s", dpid)
        self._log_topology_map()

    def _handle_LinkEvent(self, event):
        link_tuple = self._link_tuple(event.link)

        if event.added:
            self.links.add(link_tuple)
            log.info("Link added: %s", link_tuple)
        elif event.removed:
            if link_tuple in self.links:
                self.links.remove(link_tuple)
            log.info("Link removed: %s", link_tuple)

        self._log_topology_map()


def launch():
    if not core.hasComponent("openflow_discovery"):
        from pox.openflow.discovery import launch as launch_discovery

        launch_discovery()

    core.registerNew(TopologyChangeDetector)