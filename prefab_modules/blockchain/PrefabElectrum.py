"""
Prefab module to install electrum wallet
"""


from Jumpscale import j


app = j.tools.prefab._getBaseAppClass()


class PrefabElectrum(app):
    """
    Wrapps an electrum wallet application
    """
    NAME = "electrum"

    def build(self, branch=None,tag=None, revision=None, reset=False):
        """
        Will clone the electrum repository with the specificed parameters
        """
        if self.doneGet('build') and reset is False:
            return
        self.prefab.system.package.mdupdate()
        self.prefab.system.package.install("git")
        url = 'https://github.com/spesmilo/electrum.git'
        path = self.prefab.core.joinpaths(j.sal.fs.getTmpDirPath(), 'electrum')
        dest = self.prefab.tools.git.pullRepo(url,
                                              branch=branch,
                                              tag=tag,
                                              revision=revision,
                                              dest=path,
                                              ssh=False)

        self.doneSet('build')
        return dest

    def install(self, branch=None,tag="3.2.2", revision=None, reset=False):
        """
        Installs the electrum binary to the correct location
        """
        # if branch, tag, revision = None it will build form master
        if self.doneGet('install') and reset is False:
            return

        base_dir = self.build(branch=branch,tag=tag, revision=revision, reset=reset)
        electrum_bin_path = self.prefab.core.joinpaths(base_dir, 'electrum')
        if not j.sal.fs.isFile(electrum_bin_path):
            electrum_bin_path = self.prefab.core.joinpaths(electrum_bin_path, 'electrum')

        self.prefab.core.dir_ensure( "{DIR_BIN}")
        self.prefab.core.file_copy(electrum_bin_path, "{DIR_BIN}/")

        self.doneSet('install')


    def start(self, electrum_dir=None, rpcuser='user', rpcpass='pass', rpcport=7777, rpchost='localhost', testnet=False):
        """
        Starts an electrum daemon
        @param electrum_dir: Root directory for electrum daemon to store its data
        @param rpcuser: User name of RPC connection
        @param rpcpass: Password for RPC connection
        @param rpcport: Port for RPC connection
        @param rpchost: Host ipaddress/name for RPC connection
        @param testnet: If true, a connection to Bitcoin testnet will be created, otherwise the mainnet will be used
        """
        if electrum_dir is None:
            electrum_dir = self.prefab.core.joinpaths(j.dirs.DATADIR, 'electrum')
        process_name = j.sal.process.getProcessByPort(rpcport)
        if process_name and 'electrum' in process_name:
            self._logger.info("Electrum daemon is already running")
            return
        elif process_name:
            raise RuntimeError("Port {} already in use by process {}".format(rpcport, process_name))
        # not running
        if not process_name:
            base_cmd = 'electrum{} -D {}'.format(' --testnet' if testnet else '', electrum_dir)
            cmds = [
                    '{} setconfig rpcuser {}'.format(base_cmd, rpcuser),
                    '{} setconfig rpcpassword {}'.format(base_cmd, rpcpass),
                    '{} setconfig rpcport {}'.format(base_cmd, rpcport),
                    '{} setconfig rpchost {}'.format(base_cmd, rpchost),
                    '{} daemon 1>/dev/null 2>&1 &'.format(base_cmd),
                    ]
            for cmd in cmds:
                self.prefab.core.run(cmd)
