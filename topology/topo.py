from mininet.topo import Topo

class MyTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1', protocols='OpenFlow10')
        s2 = self.addSwitch('s2', protocols='OpenFlow10')

        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        self.addLink(h1, s1)
        self.addLink(h2, s2)
        self.addLink(s1, s2)

topos = {'mytopo': MyTopo}