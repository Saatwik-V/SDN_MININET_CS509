from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import MAIN_DISPATCHER, CONFIG_DISPATCHER
from ryu.controller.handler import set_ev_cls

from ryu.topology import event
from ryu.topology.api import get_switch, get_link

class TopologyDetector(app_manager.RyuApp):

    def __init__(self, *args, **kwargs):
        super(TopologyDetector, self).__init__(*args, **kwargs)
        self.topology_api_app = self

    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        switches = get_switch(self.topology_api_app, None)
        ids = [s.dp.id for s in switches]
        self.logger.info(f"Switch Added: {ids}")

    @set_ev_cls(event.EventSwitchLeave)
    def switch_leave_handler(self, ev):
        self.logger.info("Switch Removed")

    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        link = ev.link
        self.logger.info(f"Link Added: {link.src} -> {link.dst}")

    @set_ev_cls(event.EventLinkDelete)
    def link_delete_handler(self, ev):
        link = ev.link
        self.logger.info(f"Link Removed: {link.src} -> {link.dst}")