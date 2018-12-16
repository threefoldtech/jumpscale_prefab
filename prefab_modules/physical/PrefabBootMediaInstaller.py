from Jumpscale import j
import os
import time

import socket

base = j.tools.prefab._getBaseClass()


class PrefabBootMediaInstaller(base):

    def _downloadImage(self, url, redownload=False):
        base = url.split("/")[-1]
        downloadpath = "{DIR_TEMP}/%s" % base
        self.prefab.core.dir_ensure("{DIR_TEMP}")

        if redownload:
            self.prefab.core.file_unlink(downloadpath)

        if not self.prefab.core.file_exists(downloadpath):
            self.prefab.core.run("cd {DIR_TEMP};curl -L %s -O" % url)

        return base

    def _partition(self, deviceid, type):
        cmd = "parted -s /dev/%s mklabel %s mkpart primary fat32 2 200M set 1 boot on mkpart primary ext4 200M 100%%" % (
            deviceid, type)
        self.prefab.core.run(cmd)

    def _umount(self, deviceid):
        self.prefab.core.run("umount /mnt/root/boot", die=False)
        self.prefab.core.run("umount /mnt/root", die=False)
        self.prefab.core.run("umount /dev/%s1" % deviceid, die=False)
        self.prefab.core.run("umount /dev/%s2" % deviceid, die=False)

    def _mount(self, deviceid):
        self.prefab.core.run("mkfs.ext4 -F /dev/%s2" % deviceid)
        self.prefab.core.run("mkdir -p /mnt/root && mount /dev/%s2 /mnt/root" % deviceid)
        self.prefab.core.run("mkfs.vfat -F32 /dev/%s1" % deviceid)
        self.prefab.core.run("mkdir -p /mnt/root/boot && mount /dev/%s1 /mnt/root/boot" % deviceid)

    def _install(self, base):
        # We use bsdtar to support pi2 arm images.
        self.prefab.core.run("cd {DIR_TEMP} && bsdtar -vxpf %s -C /mnt/root" % base)
        self.prefab.core.run("sync")
        self.prefab.core.run("echo 'PermitRootLogin=yes'>>'/mnt/root/etc/ssh/sshd_config'")

    def _findDevices(self):
        devs = []
        for line in self.prefab.core.run("lsblk -b -o TYPE,NAME,SIZE")[1].split("\n"):
            if line.startswith("disk"):
                while line.find("  ") > 0:
                    line = line.replace("  ", " ")
                ttype, dev, size = line.split(" ")
                size = int(size)
                if size > 30000000000 and size < 32000000000:
                    devs.append((dev, size))
                if size > 15000000000 and size < 17000000000:
                    devs.append((dev, size))
                if size > 7500000000 and size < 8500000000:
                    devs.append((dev, size))
                if size > 4000000000 and size < 4100000000:
                    devs.append((dev, size))

        if len(devs) == 0:
            raise j.exceptions.RuntimeError(
                "could not find flash disk device, (need to find at least 1 of 8,16 or 32 GB size)" % devs)
        return devs

    def formatCardDeployImage(self, url, deviceid=None, part_type='msdos', post_install=None):
        """
        will only work if 1 or more sd cards found of 4 or 8 or 16 or 32 GB, be careful will overwrite the card
        executor = a linux machine

        executor=j.tools.executor.getSSHBased(addr="192.168.0.23", port=22,login="root",passwd="rooter",pushkey="ovh_install")
        executor.prefab.bootmediaInstaller.formatCards()

        :param url: Image url
        :param deviceid: Install on this device id, if not provided, will detect all devices that are 8,16,or 32GB
        :param post_install: A method that will be called with the deviceid before the unmounting of the device.
        """

        if post_install and not callable(post_install):
            raise Exception("Post install must be callable")

        base = self._downloadImage(url)

        def partition(deviceid, size, base):
            self._partition(deviceid, part_type)
            self._umount(deviceid)
            self._mount(deviceid)
            self._install(base)

            if post_install:
                post_install(deviceid)

            self._umount(deviceid)

        if deviceid is None:
            devs = self._findDevices()
        else:
            devs = [(deviceid, 0)]

        for deviceid, size in devs:
            partition(deviceid, size, base)

        return devs

    def ubuntu(self, platform="amd64", deviceid=None):
        """
        if platform none then it will use self.prefab.node.hwplatform

        example: hwplatform = rpi_2b, orangepi_plus,amd64

        """
        if platform == "amd64":
            name = self._downloadImage("http://releases.ubuntu.com/15.10/ubuntu-15.10-server-amd64.iso")
        else:
            raise j.exceptions.Input("platform not supported yet")

        path = "{DIR_TEMP}/%s" % name
        cmd = 'dd if=%s of=/dev/%s bs=4000' % (path, deviceid)
        self.prefab.core.sudo(cmd)

    def debian(self, platform="orangepi_plus", deviceid=None):
        """
        if platform none then it will use self.prefab.node.hwplatform

        example: hwplatform = rpi_2b, orangepi_plus,amd64

        """
        if platform == "orangepi_plus":
            raise RuntimeError("not implemented")
        else:
            raise j.exceptions.Input("platform not supported yet")
        # self.formatCardDeployImage(url, deviceid=deviceid)

    def arch(self, platform="rpi_2b", deviceid=None):
        """
        if platform none then it will use self.prefab.node.hwplatform

        example: hwplatform = rpi_2b, orangepi_plus,amd64

        """
        if platform == "rpi_2b":
            url = "http://archlinuxarm.org/os/ArchLinuxARM-rpi-2-latest.tar.gz"
        else:
            raise j.exceptions.Input("platform not supported yet")
        self.formatCardDeployImage(url, deviceid=deviceid)

    def g8os_arm(self, url, gid, nid, deviceid=None):
        init_tmpl = """\
        #!/usr/bin/bash

        mkdir /dev/pts
        mount -t devpts none /dev/pts
        mount -o remount,rw /

        source /etc/profile
        exec /sbin/core -gid {gid} -nid {nid} -roles g8os > /var/log/core.log 2>&1
        """

        def configure(deviceid):
            import textwrap
            init = textwrap.dedent(init_tmpl).format(gid=gid, nid=nid)
            self.prefab.core.file_write("/mnt/sbin/init", init, mode=755)

        self.formatCardDeployImage(url, deviceid=deviceid, part_type='msdos', post_install=configure)

    def g8os(self, gid, nid, platform="amd64", deviceid=None, url=None):
        """
        if platform none then it will use self.prefab.node.hwplatform

        example: hwplatform = rpi_2b, orangepi_plus,amd64

        """
        if url is None:
            if platform == "amd64":
                url = "https://stor.jumpscale.org/public/g8os.tgz"
            else:
                raise j.exceptions.Input("platform not supported yet")

        fstab_tmpl = """\
        PARTUUID={rootuuid}\t/\text4\trw,relatime,data=ordered\t0 1
        PARTUUID={bootuuid}\t/boot\tvfat\trw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=iso8859-1,shortname=mixed,errors=remount-ro    0 2
        """

        init_tmpl = """\
        #!{bash}

        mkdir /dev/pts
        mount -t devpts none /dev/pts
        mount -o remount,rw /

        source /etc/profile
        exec /usr/bin/core -gid {gid} -nid {nid} -roles g8os > /var/log/core.log 2>&1
        """

        def configure(deviceid):
            # get UUID of device
            import textwrap
            _1, bootuuid, _1 = self.prefab.core.run('blkid /dev/%s1 -o value -s PARTUUID' % deviceid)
            _2, rootuuid, _2 = self.prefab.core.run('blkid /dev/%s2 -o value -s PARTUUID' % deviceid)

            self.prefab.core.run('mount -t sysfs none /mnt/root/sys')
            self.prefab.core.run('mount -t devtmpfs none /mnt/root/dev')
            self.prefab.core.run('mount -t tmpfs none /mnt/root/tmp')
            self.prefab.core.run('mount -t proc none /mnt/root/proc')

            # add g8os section.
            self.prefab.core.run(
                'chroot /mnt/root grub-install --target=x86_64-efi --efi-directory=/boot --modules="part_gpt ext2 fat"  --removable')
            self.prefab.core.run('chroot /mnt/root grub-mkconfig -o /boot/grub/grub.cfg')

            self.prefab.core.run('umount /mnt/root/sys')
            self.prefab.core.run('umount /mnt/root/dev')
            self.prefab.core.run('umount /mnt/root/tmp')
            self.prefab.core.run('umount /mnt/root/proc')

            fstab = textwrap.dedent(fstab_tmpl).format(rootuuid=rootuuid, bootuuid=bootuuid)
            self.prefab.core.file_write("/mnt/root/etc/fstab", fstab)

            bash = '/usr/bin/bash'
            if not j.sal.fs.exists('/mnt/root/usr/bin/bash'):
                bash = '/bin/bash'

            init = textwrap.dedent(init_tmpl).format(gid=gid, nid=nid, bash=bash)
            self.prefab.core.file_write("/mnt/root/sbin/init", init, mode=755)

        self.formatCardDeployImage(url, deviceid=deviceid, part_type='gpt', post_install=configure)

    def __str__(self):
        return "prefab.bootmediaInstaller:%s:%s" % (
            getattr(self.executor, 'addr', 'local'), getattr(self.executor, 'port', ''))

    __repr__ = __str__
