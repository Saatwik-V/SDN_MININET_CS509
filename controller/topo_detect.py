from pox.core import core
from pox.lib.util import dpid_to_str
from pox.openflow import openflow_discovery
from pox.lib.packet.ethernet import ethernet
import pox.openflow.libopenflow_01 as of

log = core.getLogger()


class TopologyChangeDetector(object):
    """
    POX app with two main features:
    1. Topology Detection: Monitor switch/link events (unchanged)
    2. SDN Learning Switch: Custom MAC learning + firewall
       - Learns MAC -> port mapping
       - Installs flow rules with match-action (dl_src, dl_dst)
       - Provides MAC-based firewall blocking capability
    """

    def __init__(self):
        # ============ TOPOLOGY DETECTION ============
        self.switches = set()
        self.links = set()

        # ============ LEARNING SWITCH ============
        # MAC -> (dpid, port) mapping for intelligent forwarding
        self.mac_to_port = {}
        
        # ============ FIREWALL ============
        # Set of blocked destination MACs (can be extended via controller interface)
        self.blocked_macs = set()

        core.openflow.addListeners(self)
        core.openflow_discovery.addListeners(self)

        log.info("=" * 60)
        log.info("Controller initialized with:")
        log.info("  [1] Topology Detection (switch & link tracking)")
        log.info("  [2] Custom SDN Logic (MAC learning + firewall)")
        log.info("=" * 60)

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

    # ============ SDN LEARNING SWITCH LOGIC ============

    def _handle_PacketIn(self, event):
        """
        Handle packet_in events from switches.
        
        Logic Flow:
        1. Extract source MAC and learn its location (dpid, port)
        2. Check firewall - drop if destination MAC is blocked
        3. If destination is known:
           - Same switch: Install optimized flow rule (reducing controller involvement)
           - Different switch: Flood using spanning tree
        4. If destination is unknown: Flood packet to discover location
        """
        packet = event.parsed
        dpid = dpid_to_str(event.dpid)
        inport = event.port

        # ---- Step 1: MAC Learning ----
        # Learn where this source MAC is located
        if packet.src not in self.mac_to_port:
            self.mac_to_port[packet.src] = (dpid, inport)
            log.info("[MAC LEARN] Source %s -> switch %s, port %s", 
                    packet.src, dpid, inport)

        # ---- Step 2: Firewall Check ----
        # Drop packets destined to blocked MACs
        if packet.dst in self.blocked_macs:
            log.warning("[FIREWALL] BLOCKED: Packet to %s dropped", packet.dst)
            return  # Don't forward or flood - just drop

        # ---- Step 3 & 4: Intelligent Forwarding ----
        if packet.dst in self.mac_to_port:
            # Destination is known
            dst_dpid, dst_port = self.mac_to_port[packet.dst]

            if dst_dpid == dpid:
                # Same switch: Install flow rule for optimization
                log.info("[FLOW INSTALL] Unicast %s -> %s on switch %s", 
                        packet.src, packet.dst, dpid)
                self._install_flow_rule(event, dst_port)
            else:
                # Different switch: Flood for spanning tree handling
                log.info("[FLOOD] Inter-switch routing: %s (on %s) -> %s (on %s)",
                        packet.src, dpid, packet.dst, dst_dpid)
                self._flood_packet(event)
        else:
            # Destination unknown: Flood to discover
            log.info("[FLOOD] Unknown dest %s, flooding to learn location", 
                    packet.dst)
            self._flood_packet(event)

    def _install_flow_rule(self, event, output_port):
        """
        Install a flow rule to forward future matching packets.
        
        Match criteria:
          - dl_src: source MAC address
          - dl_dst: destination MAC address
        
        Action: output to specified port
        
        Priority: 100 (normal unicast flows)
        
        Timeouts:
          - idle_timeout: 10 sec (expire if no traffic)
          - hard_timeout: 60 sec (absolute maximum lifetime)
        """
        msg = of.ofp_flow_mod()
        msg.match = of.ofp_match()

        # Match on source and destination MAC addresses
        msg.match.dl_src = event.parsed.src     # Layer 2 Source
        msg.match.dl_dst = event.parsed.dst     # Layer 2 Destination

        # Priority and timeouts
        msg.priority = 100                       # Normal unicast priority
        msg.idle_timeout = 10                    # Remove if unused for 10s
        msg.hard_timeout = 60                    # Remove after 60s max

        # Action: forward to output port
        action = of.ofp_action_output(port=output_port)
        msg.actions.append(action)

        # Send flow modification to switch
        event.connection.send(msg)
        log.info("[FLOW RULE] Priority=%d, Idle=%ds, Hard=%ds -> port %d", 
                msg.priority, msg.idle_timeout, msg.hard_timeout, output_port)

    def _flood_packet(self, event):
        """
        Send packet_out message to flood packet to all ports except incoming port.
        Used for unknown destinations and inter-switch traffic.
        """
        msg = of.ofp_packet_out()
        msg.data = event.ofp         # Encapsulated original packet
        msg.in_port = event.port     # Incoming port

        action = of.ofp_action_output(port=of.OFPP_FLOOD)
        msg.actions.append(action)

        event.connection.send(msg)


def launch():
    """
    Launch the controller with discoveries enabled.
    
    Loads openflow_discovery automatically if not present, then registers
    our TopologyChangeDetector which provides both topology detection and
    custom SDN learning switch functionality.
    """
    if not core.hasComponent("openflow_discovery"):
        from pox.openflow.discovery import launch as launch_discovery
        launch_discovery()

    core.registerNew(TopologyChangeDetector)