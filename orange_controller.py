#!/usr/bin/env python3
"""
SDN_MININET_ORANGE - L2 Learning Switch Controller
CS509 - Software Defined Networking

A RYU OpenFlow 1.3 controller that implements a per-switch MAC learning
table and installs proactive flow rules so that subsequent packets for
a known (src, dst) pair are forwarded in hardware without being sent to
the controller again.

Run with:
    ryu-manager orange_controller.py [--ofp-tcp-listen-port 6633]
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import mac as mac_lib


class OrangeL2Switch(app_manager.RyuApp):
    """
    L2 learning switch for the Orange topology.

    Features
    --------
    - OpenFlow 1.3
    - Per-datapath MAC → port learning table
    - Proactive flow installation (idle_timeout=20s, hard_timeout=0)
    - Drops LLDP frames to prevent topology loops
    - Table-miss entry sends unknown packets to the controller
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    #: Default idle timeout (seconds) for installed unicast flows.
    FLOW_IDLE_TIMEOUT = 20
    #: Flow priority for learned unicast entries.
    FLOW_PRIORITY = 1
    #: Flow priority for the table-miss (catch-all) entry.
    TABLE_MISS_PRIORITY = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mac_to_port[dpid][mac] = port_number
        self.mac_to_port: dict[int, dict[str, int]] = {}

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=0, hard_timeout=0):
        """Install a flow entry on *datapath*."""
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

    def _send_packet_out(self, datapath, buffer_id, in_port, actions, data=None):
        """Send a PacketOut message."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

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
        """Install the table-miss flow entry when a switch connects."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Table-miss: send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(
            ofproto.OFPP_CONTROLLER,
            ofproto.OFPCML_NO_BUFFER,
        )]
        self._add_flow(datapath, self.TABLE_MISS_PRIORITY, match, actions)
        self.logger.info('Switch connected: dpid=%016x', datapath.id)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Handle PacketIn events: learn MAC addresses and forward."""
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

        # Drop LLDP frames silently
        if eth_pkt.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Initialise per-switch table if needed
        self.mac_to_port.setdefault(dpid, {})

        # Learn src → in_port
        if src_mac not in self.mac_to_port[dpid]:
            self.logger.info(
                'LEARN  dpid=%016x  %s → port %s', dpid, src_mac, in_port
            )
        self.mac_to_port[dpid][src_mac] = in_port

        # Determine output port
        if mac_lib.is_multicast(dst_mac):
            out_port = ofproto.OFPP_FLOOD
        elif dst_mac in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst_mac]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow rule for known unicast destinations
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst_mac, eth_src=src_mac)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self._add_flow(
                    datapath,
                    self.FLOW_PRIORITY,
                    match,
                    actions,
                    idle_timeout=self.FLOW_IDLE_TIMEOUT,
                )
                self._send_packet_out(datapath, msg.buffer_id, in_port, actions)
                return
            else:
                self._add_flow(
                    datapath,
                    self.FLOW_PRIORITY,
                    match,
                    actions,
                    idle_timeout=self.FLOW_IDLE_TIMEOUT,
                )

        self._send_packet_out(
            datapath,
            msg.buffer_id,
            in_port,
            actions,
            data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
        )
