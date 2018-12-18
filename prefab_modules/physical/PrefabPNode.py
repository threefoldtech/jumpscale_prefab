from Jumpscale import j


base = j.tools.prefab._BaseClass


class PrefabPNode(base):

    def _init(self):
        self.defaultArch = ['amd64', 'i686']

    @property
    def hwplatform(self):
        """
        example: hwplatform = rpi_2b, orangepi_plus, amd64
        """
        _, arch, _ = self.prefab.core.run('uname -m')

        # generic detection
        if arch == "x86_64":
            return "amd64"

        if arch == "i686":
            return "x86"

        # more precise detection
        if arch == "armv7l":
            if self.prefab.core.dir_exists('/sys/class/bcm2708_vcio'):
                return "rpi_2b"

            if self.prefab.core.file_exists('/dev/mmcblk1boot0'):
                return 'orangepi_plus'

        return None

    """
    Disk stuff
    """

    def _ensureDevName(self, device):
        if not device.startswith("/dev"):
            return "/dev/%s" % device

        return device

    def _getNeededPartitions(self):
        needed = []

        mounts = self.prefab.core.file_read('/proc/mounts').splitlines()
        for line in mounts:
            # keep root partition
            if " / " in line:
                needed.append(line)

            # keep boot partition
            if " /boot " in line:
                needed.append(line)

        swaps = self.prefab.core.file_read('/proc/swaps').splitlines()
        for line in swaps:
            # keep swap
            if line.startswith('/'):
                needed.append(line)

        final = []
        for item in needed:
            final.append(item.replace('/dev/', '').partition(' ')[0])

        return final

    def _getDisks(self):
        devices = self.prefab.core.run('lsblk -n -l -o NAME,TYPE')[1].splitlines()
        disks = []

        for line in devices:
            if "disk" in line:
                disks.append(line.partition(' ')[0])

        return disks

    def _getDisksWithExclude(self, disks, exclude):
        for disk in disks:
            for keep in exclude:
                if disk not in keep:
                    continue

                if disk in disks:
                    disks.remove(disk)

        return disks

    def _eraseDisk(self, disk):
        disk = self._ensureDevName(disk)

        self.prefab.core.run("dd if=/dev/zero of=%s bs=4M count=1" % disk)

    def _getPartitionsOnDisk(self, disk):
        disk = self._ensureDevName(disk)
        partitions = self.prefab.core.run('ls %s*' % disk)[1].splitlines()

        return partitions

    def _unmountDisk(self, disk):
        """
        Unmount all partitions in disk
        """
        partitions = self._getPartitionsOnDisk(disk)

        for partition in partitions:
            self.prefab.core.run('umount %s' % partition, die=False)

    def erase(self, keepRoot=True):
        """
        if keepRoot == True:
            find boot/root/swap partitions and leave them untouched (check if mirror, leave too)
        clean/remove all (other) disks/partitions
        """
        if self.hwplatform != "amd64":
            raise j.exceptions.Input("only amd64 hw platform supported")

        # grab the list of all disks on the machine
        disks = self._getDisks()

        if keepRoot:
            # grab list of partitions needed to keep the machine alive
            keeps = self._getNeededPartitions()
            disks = self._getDisksWithExclude(disks, keeps)

        # erasing all disks not needed
        for disk in disks:
            self._unmountDisk(disk)
            self._eraseDisk(disk)

        # commit changes to the kernel
        self.prefab.core.run("partprobe")

    def importRoot(self, source="/image.tar.gz", destination="/"):
        """
        Import and extract an archive to the filesystem

        """
        cmd = 'tar -zpxf %s -C %s' % (source, destination)
        self.prefab.core.run(cmd)

    def exportRoot(self, source="/", destination="/image.tar.gz", excludes=["\.pyc", "__pycache__"]):
        """
        Create an archive of a remote file system
        @param excludes is list of regex matches not to include while doing export
        """
        excludes_string = " ".join(["--exclude='%s'" % x for x in excludes])
        cmd = 'tar -zpcf %s --exclude=%s --one-file-system %s' % (destination, excludes_string, source)
        self.prefab.core.run(cmd)

    def exportRootStor(self, storspace, plistname, source="/", excludes=["\.pyc", "__pycache__"], removetmpdir=True):
        """
        reason to do this is that we will use this to then make the step to g8os with g8osfs (will be very small step then)

        """
        storspace.upload(plistname, source=source, excludes=excludes, removetmpdir=removetmpdir)

    def formatStorage(self, keepRoot=True, mountpoint="/storage"):
        """
        use btrfs to format/mount the disks
        use metadata & data in raid1 (if at least 2 disk)
        make sure they are in fstab so survices reboot
        """
        if self.hwplatform != "amd64":
            raise j.exceptions.Input("only amd64 hw platform supported")

        # grab the list of all disks on the machine
        disks = self._getDisks()

        if keepRoot:
            # grab list of partitions needed to keep the machine alive
            keeps = self._getNeededPartitions()
            disks = self._getDisksWithExclude(disks, keeps)

        for disk in disks:
            if len(self._getPartitionsOnDisk(disk)) > 0:
                j.exceptions.RuntimeError("Disk %s seems not empty, is the system clear ?")

        setup = []
        for disk in disks:
            setup.append(self._ensureDevName(disk))

        if not len(setup) == 0:

            disklist = ' '.join(setup)

            self.prefab.core.run('mkfs.btrfs -d raid1 %s' % disklist)
            self.prefab.core.dir_ensure(mountpoint)
            self.prefab.core.run('mount %s %s' % (setup[0], mountpoint))

        else:
            # check if no mounted btrfs partition yet and create if required
            self.prefab.storage.btrfs.subvolumeCreate(mountpoint)

    def buildG8OSImage(self):
        """

        """
        # TODO: prefab enable https://github.com/g8os/builder

    def buildArchImage(self):
        """

        """

    def installArch(self, rootsize=5):
        """
        install arch on $rootsize GB root partition
        """
        if self.hwplatform != "amd64":
            raise j.exceptions.Input("only amd64 hw platform supported")
        # manual partitioning
        # get tgz from url="https://stor.jumpscale.org/public/ubuntu....tgz"

    def installG8OS(self, rootsize=5):
        """
        install g8os on $rootsize GB root partition
        """
        if self.hwplatform != "amd64":
            raise j.exceptions.Input("only amd64 hw platform supported")
        # manual partitioning
        # get tgz from url="https://stor.jumpscale.org/public/ubuntu....tgz"
