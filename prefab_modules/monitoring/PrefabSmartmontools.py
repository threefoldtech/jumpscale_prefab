import os
from Jumpscale import j

base = j.tools.prefab._BaseClass


class PrefabSmartmontools(base):
    """
    Prefab module for smartmontools (smartctl command)
    """

    NAME = "smartmontools"

    _DOWNLOAD_URL = "http:/builds.smartmontools.org/r4592/smartmontools-6.6-0-20171104-r4592.linux-x86_64-static.tar.gz"
    _VERSION = "6.6"
    _REL_INSTALL_LOCATION = j.sal.fs.joinPaths("usr", "local", "sbin")


    def install(self):
        """
        Installs version 6.6 of smartmontools
        (apt-get version is 6.5
        Version 6.6 is needed for NVMe support)
        Ensures smartctl is installed
        """
        if self.isInstalled():
            self._logger.info("smartctl version %s is present" % self._VERSION)
            return
            
        self._logger.info("installing smartctl...")

        tmp_location = self.prefab.core.file_download(self._DOWNLOAD_URL, expand=True)

        # move downloaded binary to installation destination
        self.core.run("mv %s %s" % (j.sal.fs.joinPaths(tmp_location, self._REL_INSTALL_LOCATION, "smartctl") , j.sal.fs.joinPaths(os.sep, self._REL_INSTALL_LOCATION)))
        
        # cleanup
        self.prefab.core.dir_remove(tmp_location)

        if not self.isInstalled():
            raise RuntimeError("Failed to install Smartmontools")
    
    def isInstalled(self):
        """
        Checks smartctl of the correct version is installed
        """
        # check if command exists with a version call
        cmd = "smartctl --version"
        rc, out, err = self.prefab.core.run(cmd, die=False)
        if rc != 0:
            self._logger.warning("'smartctl --version' failed, assuming it's not installed: %s", err)
            return False

        # version number should be the second word of the first line
        version = out.split()[1]
        self._logger.debug("smartctl version '%s' found" % version)

        if version != self._VERSION:
            self._logger.warning("smartctl found but was version: %s\nNeed version %s to be installed" % (version, self._VERSION))
            return False
        
        return True
