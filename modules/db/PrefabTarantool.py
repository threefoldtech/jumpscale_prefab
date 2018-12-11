from Jumpscale import j

app = j.tools.prefab._getBaseAppClass()


class PrefabTarantool(app):

    def _init(self):
        self.git_url = 'https://github.com/tarantool/tarantool.git'

    def install(self, reset=False, branch='1.7'):
        """
        Install tarantool
        :param reset: reinstall if reset is True
        :param branch: the branch to install from
        :return:
        """
        if self.doneCheck("install", reset):
            return

        self.prefab.system.installbase.development()

        if self.core.isMac:
            # cmd="brew install tarantool"
            self.prefab.system.package.install(
                "lua,tarantool,luajit,cmake,msgpuck")

            C = """
            set -ex
            pushd $TMPDIR
            git clone http://luajit.org/git/luajit-2.0.git
            cd luajit-2.0/
            git checkout v2.1
            make && sudo make install
            ln -sf /usr/local/bin/luajit-2.1.0-beta3 /usr/local/bin/luajit
            popd

            pushd $TMPDIR
            git clone --recursive https://github.com/Sulverus/tdb
            cd tdb
            make
            sudo make install prefix=/usr//local/opt/tarantool

            sudo luarocks install redis-lua
            sudo luarocks install yaml
            sudo luarocks install penlight
            sudo luarocks install luasec OPENSSL_DIR=/usr//local/opt/openssl@1.1
            sudo tarantoolctl rocks install shard
            sudo tarantoolctl rocks install document
            sudo tarantoolctl rocks install prometheus
            sudo tarantoolctl rocks install queue
            sudo tarantoolctl rocks install expirationd
            sudo tarantoolctl rocks install connpool
            sudo tarantoolctl rocks install http
            

            # sudo luarocks install luatweetnacl

            sudo luarocks install lua-cjson

            popd
            """
            self.core.run(C)
        elif self.core.isUbuntu:
            if not self.doneCheck('dependencies', reset):
                # self.prefab.system.package.install('build-essential,cmake,coreutils,sed,libreadline-dev,'
                #                                    'libncurses5-dev,libyaml-dev,libssl-dev,libcurl4-openssl-dev,'
                #                                    'libunwind-dev,python,python-pip,python-setuptools,python-dev,'
                #                                    'python-msgpack,python-yaml,python-argparse,'
                #                                    'python-six,python-gevent,luarocks')

                # should be mainly done in self.prefab.system.installbase.development()
                self.prefab.system.package.install('build-essential,cmake,coreutils,sed,libreadline-dev,'
                                                   'libncurses5-dev,libyaml-dev,libssl-dev,libcurl4-openssl-dev,'
                                                   'libunwind-dev,luarocks')

                requirements = 'https://raw.githubusercontent.com/tarantool/test-run/master/requirements.txt'
                download_to = '/tmp/tarantool_requirements.txt'
                self.prefab.core.file_download(requirements, to=download_to, minsizekb=0)
                cmd = 'pip3 install -r %s' % download_to
                self.prefab.core.run(cmd, profile=True)

                self.doneSet('dependencies')

            tarantool = 'tarantool'
            if not self.doneCheck(tarantool, reset):
                self.prefab.runtimes.build.build(tarantool, self.git_url, branch=branch,
                                                 pre_build=['git submodule update --init --recursive'],
                                                 cmake=True, cmake_args=['-DENABLE_DIST=ON'], make=True,
                                                 make_install=True)
                self.doneSet(tarantool)

            luajit = 'luajit'
            if not self.doneCheck(luajit, reset):
                repo = 'http://luajit.org/git/luajit-2.0.git'
                post_build = ['ln -sf /usr/local/bin/luajit-2.1.0-beta3 /usr/local/bin/luajit']
                self.prefab.runtimes.build.build(luajit, repo, branch='v2.1', make=True, make_install=True,
                                                 post_build=post_build)
                self.doneSet(luajit)

            tdb = 'tdb'
            if not self.doneCheck(tdb, reset):
                repo = 'https://github.com/Sulverus/tdb'
                self.prefab.runtimes.build.build(tdb, repo,
                                                 pre_build=['git submodule update --init --recursive'], make=True,
                                                 make_install=True)
                self.doneSet(tdb)

            msgpuck = 'msgpuck'
            if not self.doneCheck(msgpuck, reset):
                repo = 'https://github.com/rtsisyk/msgpuck.git'
                self.prefab.runtimes.build.build(msgpuck, repo, cmake=True, make=True, make_install=True)
                self.doneSet('msgpuck')

            self.doneSet('install')

    def install_luarocks_rock(self, name):
        """
        Installs a luarocks rock
        :param name: name of the rock to install
        :return:
        """

        if not self.doneCheck('install'):
            raise Exception('Tarantool is not installed')

        command = """
            set -ex
            pushd /tmp
            luarocks install {name}
            popd
            """.format(name=name)
        self.core.run(command)

    def install_tarantool_rock(self, name):
        """
        Installs a tarantool rock
        :param name: name of the rock to install
        :return:
        """
        if not self.doneCheck('install'):
            raise Exception('Tarantool is not installed')
        command = """
        set -ex
        pushd /tmp
        tarantoolctl rocks install {name}
        popd
        """.format(name=name)
        self.core.run(command)

    def start(self, port=3301, passwd='admin007'):
        """
        Start tarantool in a tmux
        """
        prefab = self.prefab

        LUA = """
        box.cfg{listen = $port}
        box.schema.user.create('admin', {if_not_exists = true,password = '$passwd'})
        box.schema.user.passwd('admin','$passwd')
        require('console').start()
        """
        LUA = LUA.replace('$passwd', passwd)
        LUA = LUA.replace('$port', str(port))

        luapath = prefab.core.replace('$TMPDIR/tarantool.lua')

        self.logger.info('write lua startup to:%s' % luapath)

        prefab.core.file_write(luapath, LUA)

        cmd = 'cd $TMPDIR;rm -rf tarantool;mkdir tarantool;cd tarantool;tarantool %s' % luapath
        pm = self.prefab.system.processmanager.get()
        pm.ensure(name='tarantool', cmd=cmd, env={}, path='')

        # RESULT IS RUNNING TARANTOOL IN TMUX
