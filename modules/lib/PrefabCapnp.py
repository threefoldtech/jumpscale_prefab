from Jumpscale import j

app = j.tools.prefab._getBaseAppClass()


class PrefabCapnp(app):

    NAME = "capnp"

    def install(self, reset=False):
        """
        install capnp
        """

        if reset is False and self.isInstalled():
            return

        self.prefab.system.package.mdupdate()
        self.prefab.system.package.install(['curl', 'make', 'g++', 'python-dev'])

        #@TODO: *2 use git checkout on tag like we do for ARDB

        # c++ deps libs
        script = """
        cd $TMPDIR
        curl -O https://capnproto.org/capnproto-c++-0.5.3.tar.gz
        tar zxf capnproto-c++-0.5.3.tar.gz
        cd capnproto-c++-0.5.3
        ./configure
        make -j6 check
        sudo make install
        """
        self.prefab.core.run(script)
        # install python pacakge
        self.prefab.runtimes.pip.multiInstall(['cython', 'setuptools', 'pycapnp'], upgrade=True)
