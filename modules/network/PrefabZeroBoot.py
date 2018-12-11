import re
import time

from Jumpscale import j

base = j.tools.prefab._getBaseClass()

ZEROTIER_FIREWALL_ZONE_REGEX = re.compile(r"^firewall\.@zone\[(\d+)\]\.name='zerotier'$")
FORWARDING_FIREWALL_REGEX = re.compile(r"^firewall\.@forwarding\[(\d+)\].*?('\w+')?$")


class PrefabZeroBoot(base):

    def install(self, network_id, token, zos_version='v.1.4.1', zos_args='', reset=False):
        if not reset and self.doneCheck("install"):
            return
        # update zerotier config
        self.prefab.network.zerotier.build(install=True, reset=reset)

        # Remove sample_config
        rc, _, _ = self.prefab.core.run("uci show zerotier.sample_config", die=False)
        if rc == 0:
            self.prefab.core.run("uci delete zerotier.sample_config")
            self.prefab.core.run("uci commit")

        # Add our config
        if reset:
            zerotier_reinit = True
        else:
            rc, out, _ = self.prefab.core.run("uci show zerotier.config", die=False)
            zerotier_reinit = rc  # rc == 1 if configuration is not present
            if not zerotier_reinit:
                # Check if the configuration matches our expectations
                if not "zerotier.config.join='{}'".format(network_id) in out:
                    zerotier_reinit = True
        if zerotier_reinit:
            # Start zerotier at least one time to generate config files
            self.prefab.core.run("uci set zerotier.config=zerotier")
            self.prefab.core.run("uci set zerotier.config.enabled='1'")
            self.prefab.core.run("uci set zerotier.config.interface='wan'")  # restart ZT when wan status changed
            self.prefab.core.run("uci add_list zerotier.config.join='{}'".format(network_id))  # Join zerotier network
            self.prefab.core.run("uci set zerotier.config.secret='generate'")  # Generate secret on the first start
            self.prefab.core.run("uci commit")
            self.prefab.core.run("/etc/init.d/zerotier enable")
            self.prefab.core.run("/etc/init.d/zerotier start")

        # Join Network
        zerotier_client = j.clients.zerotier.get(data={"token_": token})
        self.prefab.network.zerotier.network_join(network_id, zerotier_client=zerotier_client)

        # update TFTP and DHCP
        self.prefab.core.run("uci set dhcp.@dnsmasq[0].enable_tftp='1'")
        self.prefab.core.run("uci set dhcp.@dnsmasq[0].tftp_root='/opt/storage/'")
        self.prefab.core.run("uci set dhcp.@dnsmasq[0].dhcp_boot='pxelinux.0'")
        self.prefab.core.run("uci commit")

        self.prefab.core.dir_ensure('/opt/storage')
        self.prefab.core.run("opkg install curl ca-bundle")
        self.prefab.core.run("curl https://download.gig.tech/pxe.tar.gz -o /opt/storage/pxe.tar.gz")
        self.prefab.core.run("tar -xzf /opt/storage/pxe.tar.gz -C /opt/storage")
        self.prefab.core.run("cp -r /opt/storage/pxe/* /opt/storage")
        self.prefab.core.run("rm -rf /opt/storage/pxe")
        self.prefab.core.run('sed -i "s|a84ac5c10a670ca3|%s/%s|g" /opt/storage/pxelinux.cfg/default' % (network_id,
                                                                                                        zos_args))
        self.prefab.core.run('sed -i "s|zero-os-master|%s|g" /opt/storage/pxelinux.cfg/default' % zos_version)

        # this is needed to make sure that network name is ready
        for _ in range(12):
            try:
                network_device_name = self.prefab.network.zerotier.get_network_interface_name(network_id)
                break
            except KeyError:
                time.sleep(5)
        else:
            raise RuntimeError("Unable to join network within 60 seconds!")
        self.prefab.core.run("uci set network.{0}=interface".format(network_device_name))
        self.prefab.core.run("uci set network.{0}.proto='none'".format(network_device_name))
        self.prefab.core.run("uci set network.{0}.ifname='{0}'".format(network_device_name))

        try:
            zone_id = self.get_zerotier_firewall_zone()
        except KeyError:
            self.prefab.core.run("uci add firewall zone")
            zone_id = -1

        self.prefab.core.run("uci set firewall.@zone[{0}]=zone".format(zone_id))
        self.prefab.core.run("uci set firewall.@zone[{0}].input='ACCEPT'".format(zone_id))
        self.prefab.core.run("uci set firewall.@zone[{0}].output='ACCEPT'".format(zone_id))
        self.prefab.core.run("uci set firewall.@zone[{0}].name='zerotier'".format(zone_id))
        self.prefab.core.run("uci set firewall.@zone[{0}].forward='ACCEPT'".format(zone_id))
        self.prefab.core.run("uci set firewall.@zone[{0}].masq='1'".format(zone_id))
        self.prefab.core.run("uci set firewall.@zone[{0}].network='{1}'".format(zone_id, network_device_name))

        self.add_forwarding('lan', 'zerotier')
        self.add_forwarding('zerotier', 'lan')

        self.prefab.core.run("uci commit")

        self.doneSet("install")

    def get_zerotier_firewall_zone(self):
        _, out, _ = self.prefab.core.run("uci show firewall")
        for line in out.splitlines():
            m = ZEROTIER_FIREWALL_ZONE_REGEX.match(line)
            if m:
                return int(m.group(1))
        raise KeyError("Zerotier zone in firewall configuration was not found!")

    def add_forwarding(self, dest, src):
        _, out, _ = self.prefab.core.run("uci show firewall")
        forwards = dict()
        for line in out.splitlines():
            m = FORWARDING_FIREWALL_REGEX.match(line)
            if m:
                if line.endswith("=forwarding"):
                    forwards[m.group(1)] = dict()
                elif ".dest=" in line:
                    forwards[m.group(1)]['dest'] = m.group(2)
                elif ".src=" in line:
                    forwards[m.group(1)]['src'] = m.group(2)
        if {'dest': "'%s'" % dest, 'src': "'%s'" % src} in forwards.values():
            return
        self.prefab.core.run("uci add firewall forwarding")
        self.prefab.core.run("uci set firewall.@forwarding[-1]=forwarding")
        self.prefab.core.run("uci set firewall.@forwarding[-1].dest='%s'" % dest)
        self.prefab.core.run("uci set firewall.@forwarding[-1].src='%s'" % src)
