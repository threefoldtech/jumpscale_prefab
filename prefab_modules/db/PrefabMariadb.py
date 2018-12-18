from Jumpscale import j
import time


app = j.tools.prefab._BaseAppClass


class PrefabMariadb(app):
    NAME = 'mariadb'
    PORT = '3306'

    def install(self, start=False, reset=False):
        """install and configure mariadb

        Keyword Arguments:
            start {bool} -- flag to specify whether to start mariadb on installation (default: {False})
            reset {bool} -- flag to specify whether to force install (default: {False})
        """

        if self.doneCheck("install", reset):
            return
        self.prefab.system.package.install("mariadb-server")
        self.prefab.core.dir_ensure("/data/db")
        self.prefab.core.dir_ensure("/var/run/mysqld")
        script = """
        chown -R mysql.mysql /data/db/
        chown -R mysql.mysql /var/run/mysqld
        mysql_install_db --basedir=/usr --datadir=/data/db
        """
        self.prefab.core.run(script)

        self.doneSet("install")

        if start:
            try:
                self.start()
            except Exception:
                j.logger.get().warning("MySql didn't started, maybe it's "
                        "already running or the port 3306 is used by other service")

    def start(self):
        """Start mariadb
        """

        cmd = '/usr/sbin/mysqld --basedir=/usr --datadir=/data/db \
                --plugin-dir=/usr/lib/mysql/plugin --log-error=/dev/log/mysql/error.log \
                --pid-file=/var/run/mysqld/mysqld.pid \
                --socket=/var/run/mysqld/mysqld.sock --port={}'.format(self.PORT)

        pm = self.prefab.system.processmanager.get()
        pm.ensure('mariadb', cmd=cmd)

    def init(self):
        """Initialize the data directory
        """
        cmd = 'mysql_install_db'
        self.prefab.core.run(cmd)

    def db_export(self, dbname, targetdir):
        """export specified database

        Arguments:
            db_name {string} -- name of the database to be exported
            target_dir    {string} -- dir to which db will be exported to
        """

        target = j.sal.fs.joinPaths(
            targetdir, 'datadump-' + str(int(time.time())) + '.sql')
        cmd = 'mysqldump {} > {}'.format(dbname, target)
        self.prefab.core.run(cmd)

    def db_import(self, dbname, sqlfile):
        """export specified database

        Arguments:
            dbname   {string} -- name of the database that sqlfile will be imported to
            sqlfile  {string} -- sqlfile path to be imported
        """
        self._create_db(dbname)
        cmd = 'mysql {dbname} < {sqlfile}'.format(
            dbname=dbname, sqlfile=sqlfile)
        self.prefab.core.run(cmd)

    def user_create(self, username, password=''):
        """creates user with no rights

        Arguments:
            username   {string} -- username to be created
            password   {string} -- if provided will be the creted user password
        """
        if password:
            password = "IDENTIFIED BY '{password}'".format(password=password)
        cmd = 'echo "CREATE USER {username}@localhost {password}"| mysql'.format(username=username, password=password)
        self.prefab.core.run(cmd, die=False)

    def admin_create(self, username, password=''):
        """creates user with all rights

        Arguments:
            username   {string} -- username to be created
            password   {string} -- if provided will be the creted user password
        """

        self.user_create(username, password=password)
        cmd = 'echo "GRANT ALL PRIVILEGES ON *.* TO \'{username}\'@\'localhost\' WITH GRANT OPTION;" | mysql'.format(
            username=username)
        self.prefab.core.run(cmd, die=False)

    def sql_execute(self, dbname, sql):
        """[summary]

        Arguments:
            dbname {string} -- database name that query will run against
            sql    {string} -- sql query to be run
        """
        if not dbname:
            dbname = ''
        cmd = 'mysql -e "{}" {}'.format(sql, dbname)
        self.prefab.core.run(cmd)

    def user_db_access(self, username, dbname):
        """give use right to this database (fully)
        username   {string} -- username to be granted the access
        dbname     {string} -- database name to which access would be granted
        """

        cmd = 'echo "GRANT ALL PRIVILEGES ON {dbname}.* TO {username}@localhost WITH GRANT OPTION;" | mysql'.format(
            dbname=dbname, username=username)
        self.prefab.core.run(cmd, die=False)

    def _create_db(self, dbname):
        cmd = 'echo "CREATE DATABASE {dbname}" | mysql'.format(dbname=dbname)
        self.prefab.core.run(cmd, die=False)
