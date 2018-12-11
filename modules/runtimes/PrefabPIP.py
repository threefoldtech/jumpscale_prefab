
from Jumpscale import j

base = j.tools.prefab._getBaseClass()


class PrefabPIP(base):

    # -----------------------------------------------------------------------------
    # PIP PYTHON PACKAGE MANAGER
    # -----------------------------------------------------------------------------

    def _ensure(self, reset=False):

        # python should already be requirement, do not install !! (despiegk)
        # self.prefab.system.package.install('python3.5')
        # self.prefab.system.package.install('python3-pip')


        if self.doneCheck("ensure", reset):
            return

        if self.prefab.platformtype.isUbuntu and self.prefab.platformtype.osversion=='18.04':
            #get-pip does not work
            self.prefab.system.package.install("python3-pip")
            self.doneSet("ensure")
            return

        tmpdir = self.replace("$TMPDIR")
        cmd1 = """
            #important remove olf pkg_resources, will conflict with new pip
            rm -rf /usr/lib/python3/dist-packages/pkg_resources
            cd %s/
            rm -rf get-pip.py
            """ % tmpdir
        self.prefab.core.execute_bash(cmd1)
        cmd2 = "cd %s/ && curl https://bootstrap.pypa.io/get-pip.py >  get-pip.py" % tmpdir
        self.prefab.core.run(cmd2)
        cmd3 = "python3 %s/get-pip.py" % tmpdir
        self.prefab.core.run(cmd3)

        self.doneSet("ensure")

    # def package_upgrade(self, package):
    #     '''
    #     The "package" argument, defines the name of the package that will be upgraded.
    #     '''
    #     self._ensure()
    #     # self.prefab.core.set_sudomode()
    #     self.prefab.core.run('pip3 install --upgrade %s' % (package))

    def install(self, package=None, upgrade=True, reset=False):
        self.logger.warning("do no use install, use package_install")
        return self.package_install(package,upgrade,reset)

    def package_install(self, package=None, upgrade=True, reset=False):
        '''
        The "package" argument, defines the name of the package that will be installed.

        package can be list or comma separated list of packages as well

        '''
        self._ensure()
        packages = j.data.text.getList(package, "str")

        cmd = ""

        todo = []
        for package in packages:
            if reset or not self.doneGet("pip_%s" % package):
                todo.append(package)
                if self.prefab.core.isArch:
                    if package in ["credis", "blosc", "psycopg2"]:
                        continue

                if self.prefab.core.isCygwin and package in ["psycopg2", "psutil", "zmq"]:
                    continue

                cmd += "pip3 install %s" % package
                if upgrade:
                    cmd += " --upgrade"
                cmd += "\n"

        if len(todo) > 0:
            self.prefab.core.run(cmd)

        for package in todo:
            self.doneSet("pip_%s" % package)

    def package_remove(self, package):
        '''
        The "package" argument, defines the name of the package that will be ensured.
        The argument "r" referes to the requirements file that will be used by pip and
        is equivalent to the "-r" parameter of pip.
        Either "package" or "r" needs to be provided
        '''
        if not self.doneGet("pip_remove_%s" % package):
            return self.prefab.core.run('pip3 uninstall %s' % (package))
            self.doneSet("pip_remove_%s" % package)
    #
    # def multiInstall(self, packagelist, upgrade=True, reset=False):
    #     """
    #     @param packagelist is text file and each line is name of package
    #     can also be list
    #
    #     e.g.
    #         # influxdb
    #         # ipdb
    #         # ipython
    #         # ipython-genutils
    #         itsdangerous
    #         Jinja2
    #         # marisa-trie
    #         MarkupSafe
    #         mimeparse
    #         mongoengine
    #
    #     if doneCheckMethod!=None:
    #         it will ask for each pip if done or not to that method, if it returns true then already done
    #
    #     """
    #     if j.data.types.string.check(packagelist):
    #         packages = packagelist.split("\n")
    #     elif j.data.types.list.check(packagelist):
    #         packages = packagelist
    #     else:
    #         raise j.exceptions.Input(
    #             'packagelist should be string or a list. received a %s' % type(packagelist))
    #
    #     to_install = []
    #     for dep in packages:
    #         dep = dep.strip()
    #         if dep is None or dep == "" or dep[0] == '#':
    #             continue
    #         to_install.append(dep)
    #
    #     for item in to_install:
    #         self.install(item, reset=reset)
