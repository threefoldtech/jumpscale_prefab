from Jumpscale import j


app = j.tools.prefab._getBaseAppClass()


class PrefabRipple(app):
    NAME = "rippled"

    def build(self, reset=False):
        """Get/Build the binaries of ripple
        Keyword Arguments:
            reset {bool} -- reset the build process (default: {False})
        """

        if self.doneGet('build') and reset is False:
            return
        
        # rfer to: https://ripple.com/build/rippled-setup/#installing-rippled
    
        self.prefab.system.package.install(['yum-utils', 'alien'])
        cmds = """
        rpm -Uvh https://mirrors.ripple.com/ripple-repo-el7.rpm
        yumdownloader --enablerepo=ripple-stable --releasever=el7 rippled
        rpm --import https://mirrors.ripple.com/rpm/RPM-GPG-KEY-ripple-release && rpm -K rippled*.rpm
        alien -i --scripts rippled*.rpm && rm rippled*.rpm

        """
        self.prefab.core.run(cmds)

        self.doneSet('build')

    def install(self, reset=False):
        if self.doneGet('install') and reset is False:
            return

        cmds = """
        cp /opt/ripple/bin/rippled $BINDIR/
        """
        self.prefab.core.run(cmds)

        self.doneSet('install')