#!/usr/bin/env python3
"""
SDN_MININET_ORANGE - Firewall / ACL Controller
CS509 - Software Defined Networking

Extends the L2 learning switch with a simple stateless firewall.
Access-control rules are defined in FIREWALL_RULES below.  Each rule
is a dictionary whose keys map to OFPMatch fields.  Matching traffic
is dropped (no output actions).

Run with:
    ryu-manager firewall_controller.py [--ofp-tcp-listen-port 6633]
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, ether_types, in_proto
from ryu.lib import mac as mac_lib


# ---------------------------------------------------------------------------
# Firewall rules
# Each entry is a dict of OFPMatch keyword arguments.  Matching traffic is
# silently dropped with a high-priority flow rule installed on every switch.
# ---------------------------------------------------------------------------
FIREWALL_RULES = [
    # Block all traffic from h1 (10.0.0.1) to h16 (10.0.0.16)
    {'eth_type': ether_types.ETH_TYPE_IP,
     'ipv4_src': '10.0.0.1',
     'ipv4_dst': '10.0.0.16'},
    # Block TCP port 23 (Telnet) anywhere in the network
    {'eth_type': ether_types.ETH_TYPE_IP,
     'ip_proto': in_proto.IPPROTO_TCP,
     'tcp_dst': 23},
]

#: Priority for drop rules (higher than unicast forwarding rules).
FIREWALL_PRIORITY = 100
#: Priority for learned unicast forwarding rules.
FORWARD_PRIORITY = 1
#: Priority for the table-miss catch-all.
TABLE_MISS_PRIORITY = 0
#: Idle timeout for forwarding rules (seconds).
FLOW_IDLE_TIMEOUT = 20


class OrangeFirewall(app_manager.RyuApp):
    """
    L2 learning switch with stateless ACL firewall.

    On switch connect
    -----------------
    1. Table-miss entry → send to controller.
    2. Drop rules from FIREWALL_RULES are installed at FIREWALL_PRIORITY.

    On PacketIn
    -----------
    - MAC learning as in OrangeL2Switch.
    - Unicast forwarding rules are installed at FORWARD_PRIORITY (<
      FIREWALL_PRIORITY) so that drop rules always win.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mac_to_port[dpid][mac] = port_number
        self.mac_to_port: dict[int, dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(
            ofproto.OFPIT_APPLY_ACTIONS, actions
        )]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)

    def _install_firewall_rules(self, datapath):
        """Push all FIREWALL_RULES as drop entries onto *datapath*."""
        parser = datapath.ofproto_parser
        for rule in FIREWALL_RULES:
            match = parser.OFPMatch(**rule)
            # Empty actions list → drop
            self._add_flow(datapath, FIREWALL_PRIORITY, match, [])
            self.logger.info(
                'FIREWALL dpid=%016x  installed drop rule: %s',
                datapath.id, rule,
            )

    def _send_packet_out(self, datapath, buffer_id, in_port, actions, data=None):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Table-miss entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(
            ofproto.OFPP_CONTROLLER,
            ofproto.OFPCML_NO_BUFFER,
        )]
        self._add_flow(datapath, TABLE_MISS_PRIORITY, match, actions)

        # Firewall drop rules
        self._install_firewall_rules(datapath)

        self.logger.info('Switch connected: dpid=%016x', datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        if eth_pkt is None:
            return

        dst_mac = eth_pkt.dst
        src_mac = eth_pkt.src

        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        self.mac_to_port.setdefault(dpid, {})
        if src_mac not in self.mac_to_port[dpid]:
            self.logger.info(
                'LEARN  dpid=%016x  %s → port %s', dpid, src_mac, in_port
            )
        self.mac_to_port[dpid][src_mac] = in_port

        if mac_lib.is_multicast(dst_mac):
            out_port = ofproto.OFPP_FLOOD
        elif dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port, eth_dst=dst_mac, eth_src=src_mac
            )
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self._add_flow(
                    datapath, FORWARD_PRIORITY, match, actions,
                    idle_timeout=FLOW_IDLE_TIMEOUT,
                )
                self._send_packet_out(datapath, msg.buffer_id, in_port, actions)
                return
            else:
                self._add_flow(
                    datapath, FORWARD_PRIORITY, match, actions,
                    idle_timeout=FLOW_IDLE_TIMEOUT,
                )

        self._send_packet_out(
            datapath,
            msg.buffer_id,
            in_port,
            actions,
            data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
        )
