from jumpscale import j
import os
import gzip
import pwd
import grp


class StorScripts():
    # create hexa directory tree
    # /00/00, /00/01, /00/02, ..., /ff/fe, /ff/ff

    def initTree(self, root):
        return """
        import os

        root = "%s"
        for a in range(0, 256):
            lvl1 = os.path.join(root, format(a, '02x'))
            os.mkdir(lvl1)

            for b in range(0, 256):
                lvl2 = os.path.join(lvl1, format(b, '02x'))
                os.mkdir(lvl2)

        """ % root

    # check if a set of keys exists
    def exists(self, root, keys):
        return """
import os
import json

root = "%s"
keys = json.loads('''%s''')
data = {}

def hashPath(root, hash):
    return os.path.join(root, hash[:2], hash[2:4], hash)

for key in keys:
    data[key] = os.path.isfile(hashPath(root, key))

self.logger.info(json.dumps(data))

        """ % (root, j.data.serializer.json.dumps(keys))

    # check consistancy and expirations of files
    def check(self, root, keys):
        return """
        import os
        import json
        import hashlib
        import time

        root = "%s"
        keys = json.loads('''%s''')
        data = {}

        def hashfile(filename, blocksize=65536):
            afile = open(filename, 'rb')
            hasher = hashlib.md5()
            buf = afile.read(blocksize)
            while len(buf) > 0:
                hasher.update(buf)
                buf = afile.read(blocksize)

            afile.close()
            return hasher.hexdigest()

        def loadMetadata(metafile):
            with open(metafile, 'r') as f:
                data = f.read()

            return json.loads(data)

        def checkMeta(fullpath):
            metafile = fullpath + ".meta"
            metadata = loadMetadata(metafile)

            if time.time() >= metadata["expiration"]:
                # os.unlink(fullpath)
                # os.unlink(metafile)
                return "expired"

            return True

        def checkFile(dirname, filename):
            fullpath = os.path.join(dirname, filename)

            if not os.path.isfile(fullpath):
                return "not found"

            if hashfile(fullpath) != os.path.basename(filename):
                # os.unlink(fullpath)
                # delete metafile if exists ?
                return "corrupted"

            if os.path.isfile(fullpath + ".meta"):
                return checkMeta(fullpath)

            return True

        def checkContent(root):
            for dirname, dirnames, filenames in os.walk(root):
                for filename in filenames:
                    if filename.endswith(".meta"):
                        continue

                    data[filename] = checkFile(dirname, filename)

        # check the whole storagespace
        if len(keys) == 0:
            for a in range(0, 256):
                lvl1 = os.path.join(root, format(a, '02x'))

                for b in range(0, 256):
                    checkContent(os.path.join(lvl1, format(b, '02x')))

        # check for specific keys
        else:
            for key in keys:
                path = os.path.join(key[:2], key[2:4], key)
                data[key] = checkFile(root, path)

        self.logger.info(json.dumps(data))

        """ % (root, j.data.serializer.json.dumps(keys))

    # get metadata of a set of keys
    def getMetadata(self, root, keys):
        return """
        import os
        import json
        import gzip
        import random

        root = "%s"
        keys = json.loads('''%s''')
        data = {}

        def loadMetadata(metafile):
            with open(metafile, 'r') as f:
                data = f.read()

            return json.loads(data)

        def getMetadata(dirname, filename, key):
            fullpath = os.path.join(dirname, filename)
            metapath = fullpath + ".meta"

            if os.path.isfile(metapath):
                data[key] = loadMetadata(metapath)

        for key in keys:
            path = os.path.join(key[:2], key[2:4], key)
            getMetadata(root, path, key)

        output = json.dumps(data)
        content = gzip.compress(bytes(output, 'utf-8'))
        tmpfile = '/tmp/md-gzip-' + str(random.randrange(1, 10000000)) + '.gz'

        with open(tmpfile, 'w+b') as f:
            f.write(content)

        self.logger.info(tmpfile)

        """ % (root, j.data.serializer.json.dumps(keys))

    # set metadata for a set of keys
    def setMetadata(self, root, keys, metadata):
        return """
        import os
        import json
        import gzip

        root = "%s"
        keys = json.loads('''%s''')
        meta = '''%s'''
        data = {}

        def setMetadata(dirname, filename, key, meta):
            fullpath = os.path.join(dirname, filename)
            metafile = fullpath + ".meta"

            with open(metafile, 'w') as f:
                f.write(meta)

            data[key] = True

        for key in keys:
            path = os.path.join(key[:2], key[2:4], key)
            setMetadata(root, path, key, meta)

        self.logger.info(json.dumps(data))

        """ % (root, j.data.serializer.json.dumps(keys), j.data.serializer.json.dumps(metadata))

    def tarball(self, root, keys, target):
        return """
import os
import json
import subprocess

root = "%s"
keys = json.loads('''%s''')
targ = '''%s'''
item = targ + '.list'

os.chdir(root)

if os.path.isfile(targ):
    os.unlink(targ)

with open(item, 'w') as f:
    for key in keys:
        f.write(os.path.join(key[:2], key[2:4], key) + "\\n")

subprocess.call(['tar', '-cT', item, '-f', targ])
os.unlink(item)

self.logger.info(targ)

        """ % (root, j.data.serializer.json.dumps(keys), target)


base = j.tools.prefab._getBaseClass()


class PrefabStor(base):

    def __init__(self, executor, prefab):
        self.executor = executor
        self.prefab = prefab
        self.root = "/storage/jstor/"

        self._config = None
        self.scripts = StorScripts()

        self.storagespaces = {}  # paths of root of hash tree

    def help(self):
        C = """
        #to change root:
        j.tools.prefab.local.stor.root="/someroot"
        sp=j.tools.prefab.local.stor.getStorageSpace("main")
        #get the file list, it creates the hashes and shows what it has found
        fl=sp.flist("/Volumes/Untitled/_backup/books/")
        #upload the list
        sp.upload(fl)
        """
        self.logger.info(C)

    @property
    def config(self):
        if self._config is None:
            path = j.sal.fs.joinPaths(self.root, "config.yaml")
            if self.prefab.core.file_exists(path):
                self._config = j.data.serializer.yaml.load(self.prefab.file_read(self.root, "config.yaml"))

        return self._config

    @config.setter
    def config(self, key, value):
        self.config  # populate if it doesn't exist
        self._config[key] = value
        serialized = j.data.serializer.dumps(self._config)
        path = j.sal.fs.joinPaths(self.root, "config.yaml")
        self.prefab.core.file_write(path, serialized)

    def enableServerHTTP(self):
        self.config["httpserver"] = {"running": False}

    def enableServerRSYNC(self):
        self.config["rsyncserver"] = {"running": False}

    def existsStorageSpace(self, name):
        """
        Check if specific storagespace exists
        """
        return self.prefab.core.dir_exists(j.sal.fs.joinPaths(self.root, name))

    def getStorageSpace(self, name):
        """
        Return a storagespace object
        """
        if name not in self.storagespaces:
            sp = StorSpace(self, name)
            self.storagespaces[name] = sp

        return self.storagespaces[name]

    def removeStorageSpace(self, name):
        """
        Remove a complete storagespace and all it's content
        """
        if not self.existsStorageSpace(name):
            return None

        path = j.sal.fs.joinPaths(self.root, name)
        self.prefab.core.dir_remove(path, recursive=True)

        if name in self.storagespaces:
            del self.storagespaces[name]

    def restart(self):
        self.stop()
        self.start()

    def start(self):
        for key, stor in self.storagespaces.items():
            #... create rsync & caddy config file & send to remote server
            pass

        if "httpserver" in self.config:
            if self.config["httpserver"]["running"] is False:
                # start caddy in tmux, there should be prefab extension for this
                self.prefab.apps.caddy.start(self.config['httpserver']['ssl'])

        if "rsyncserver" in self.config:
            if self.config["rsyncserver"]["running"] is False:
                # start rsync in tmux, there should be prefab extension for this
                j.sal.rsync.getServer(self.config['rsyncserver']['name']).start()


class StorSpace(object):
    """
    each file is stored in

    $self.path/ab/cd/$hash
    ab & cd are first 2 and then next 2 hash chars

    OPTIONALLY:
    $self.path/ab/cd/$hash.meta is stored which has some metadata about the file
    """

    def __init__(self, stor, name, public=True):
        self.prefab = stor.prefab
        self.executor = stor.executor
        self.stor = stor

        self.spacepath = j.sal.fs.joinPaths(stor.root, "namespaces", name)
        self.archivepath = j.sal.fs.joinPaths(stor.root, "archives", name)
        self.flistpath = j.sal.fs.joinPaths(stor.root, "flist", name)
        self._config = {}

        self.init()

    def init(self):
        self.prefab.core.dir_ensure(self.spacepath)
        self.prefab.core.dir_ensure(self.archivepath)
        self.prefab.core.dir_ensure(self.flistpath)

    """
    def enableServerHTTP(self, name, browse=True, secrets=[]):
        if "HTTP" not in self.config:
            self.config["HTTP"] = {}

        self.config["HTTP"][name] = {"secrets": secrets, "browse": browse}
        # make sure we only configure caddy when this entry exists
        # when browse false then users can download only when they know the full path
        # secrets is http authentication

        # there can be multiple entries for webserver un different names e.g. 1
        # browse with passwd, 1 anonymous with no browse, ...

    def enableServerRSYNC(self, name, browse=True, secrets=[]):
        if "RSYNC" not in self.config:
            self.config["RSYNC"] = {}

        self.config["RSYNC"][name] = {"secrets": secrets, "browse": browse}
    """

    '''
    @property
    def config(self):
        if self._config == {}:
            path = j.sal.fs.joinPaths(self.path, "config.yaml")

            if self.prefab.core.file_exists(path):
                yaml = self.prefab.core.file_read(path)
                self._config = j.data.serializer.yaml.loads(yaml)

        return self._config
    '''

    '''
    @config.setter
    def config(self, val):
        #check dict
        #store in config also remote serialized !!!
        pass

    def configCommit(self):
        yaml = j.data.serializer.yaml.dumps(self.config)
        path = j.sal.fs.joinPaths(self.path, "config.yaml")
        self.prefab.core.file_write(path, yaml)
    '''

    def hashPath(self, hash):
        return '%s/%s/%s' % (hash[:2], hash[2:4], hash)

    '''
    def metadataFile(self, path):
        return "%s.meta" % path

    def metadata(self, expiration=None, tags=None):
        """
        Build a representation used internaly to expose metadata
        """
        if expiration or tags:
            meta = {}
            meta["expiration"] = expiration
            meta["tags"] = tags
            return meta

        return None
    '''

    def file_upload(self, source, storpath, expiration=None, tags=None):
        """
        Upload a file to a specific location in the storagespace
        @param expiration: timestamp after when file could be discarded
        """
        # small protection against directory transversal
        # better approch: os.path.abspath ?
        storpath = storpath.replace('../', '')

        filepath = j.sal.fs.joinPaths(self.spacepath, storpath)
        path = j.sal.fs.getDirName(filepath)

        # be sur that remote directory exists
        self.prefab.core.dir_ensure(path)
        self.prefab.core.upload(source, filepath)

        '''
        metadata = self.metadata(expiration, tags)
        if metadata:
            # upload metadata only if defined
            # NOTE: metadata are saved in json because code executed
            # on remote side does probably not have yaml parser installed
            # json parser in python should be able out-of-box
            md = j.data.serializer.json.dumps(metadata)
            self.prefab.core.file_write(self.metadataFile(filepath), md)
        '''

        return True

    def flist_upload(self, source, flistname):
        """
        Upload a flist file to the destination namespace
        """
        # small protection against directory transversal
        # better approch: os.path.abspath ?
        storpath = flistname.replace('../', '')

        filepath = j.sal.fs.joinPaths(self.flistpath, flistname)
        path = j.sal.fs.getDirName(filepath)

        # be sur that remote directory exists
        self.prefab.core.dir_ensure(path)
        self.prefab.core.upload(source, filepath)

        return True

    def file_download(self, storpath, dest, chmod=None, chown=None):
        """
        Download a file from the storagespace to a specific location
        """
        # small protection against directory transversal
        storpath = storpath.replace('../', '')

        filepath = j.sal.fs.joinPaths(self.spacepath, storpath)
        self.prefab.core.download(filepath, dest)

        if chmod:
            j.sal.fs.chmod(dest, chmod)

        if chown:
            # FIXME: group ?
            j.sal.fs.chown(dest, chown)

        '''
        # checking if there is metadata
        metafile = self.metadataFile(storpath)
        if self.prefab.core.file_exists(metafile):
            return self.prefab.core.file_read(metafile)
        '''

        return True

    def flist_download(self, flistfile, dest):
        """
        Download a flist from the storagespace namespace to a specific location
        """
        # small protection against directory transversal
        storpath = flistfile.replace('../', '')

        filepath = j.sal.fs.joinPaths(self.flistpath, storpath)
        self.prefab.core.download(filepath, dest)

        return True

    def file_remove(self, storpath):
        """
        Remove a given file from the storagespace
        """
        # small protection against directory transversal
        storpath = storpath.replace('../', '')

        path = j.sal.fs.joinPaths(self.spacepath, storpath)

        if not self.prefab.core.file_exists(path):
            return False

        # remove file
        self.prefab.core.file_unlink(path)

        # remove metadata if exists
        metadata = self.metadataFile(path)
        if self.prefab.core.file_exists(metadata):
            self.prefab.core.file_unlink(metadata)

        return True

    def exists(self, keys=[]):
        """
        Check if a set of keys exists. Returns a list which contains hash and bool
        """
        script = self.stor.scripts.exists(self.spacepath, keys)
        data = self.prefab.core.execute_python(script, showout=False)[1]
        return j.data.serializer.json.loads(data)

    def get(self, key, dest, chmod=None, chown=None):
        """
        Download a specific key (hash) from storage and save it locally
        """
        return self.file_download(self.hashPath(key), dest, chmod, chown)

    def set(self, source, expiration=None, tags=None):
        """
        Upload a file and save it to the storage. It's hash will be returned
        @param expiration: timestamp after when file could be discarded
        """
        checksum = j.data.hash.md5(source)

        # do not upload file if already exists
        existing = self.exists([checksum])
        if existing[checksum]:
            return True

        hashpath = self.hashPath(checksum)
        self.logger.info(hashpath)

        # uploading file, if success, return the hash
        if self.file_upload(source, hashpath, expiration, tags):
            return checksum

        return False

    def delete(self, key):
        """
        Delete a key in the storagespace
        """
        return self.file_remove(self.hashPath(key))

    def check(self, keys=[]):
        """
        Check consistancy and validity of a set of keys in the storagespace
        """
        script = self.stor.scripts.check(self.spacepath, keys)
        data = self.prefab.core.execute_python(script)[1]

        return j.data.serializer.json.loads(data)

    '''
    def getMetadata(self, keys):
        """
        Get metadata content for a set of keys from the storagespace
        """
        script = self.stor.scripts.getMetadata(self.path, keys)
        data = self.prefab.core.execute_python(script)[1]

        return j.data.serializer.json.loads(self.getResponse(data))

    def setMetadata(self, keys, metadata):
        """
        Set (same) metadata for a set of keys
        @param metadata: a metadata type created with self.metadata
        """
        script = self.stor.scripts.setMetadata(self.path, keys, metadata)
        data = self.prefab.core.execute_python(script)
        return True
    '''

    def getResponse(self, remote):
        if not remote.startswith('/tmp'):
            # output seems not correct
            return False

        localfile = '/tmp/jstor-response-%s.gz' % j.sal.fs.getBaseName(remote)
        self.prefab.core.download(localfile, remote)
        self.prefab.core.file_unlink(remote)

        with open(localfile, 'rb') as f:
            content = f.read()

        j.sal.fs.remove(localfile)

        response = gzip.decompress(content).decode('utf-8')

        return response

    def _clearFile(self, obj):
        obj.mode = 0o0600
        obj.uid = 0
        obj.gid = 0
        obj.uname = 'root'
        obj.gname = 'root'

        return obj

    def upload(self, flistname, host=None, source="/",
               excludes=[r'/__pycache__/', r'(.*)\.pyc$'], removetmpdir=True, metadataStorspace=None):
        """
        Upload a complete directory:
         - from 'host' (if it's an executor)
           Note: you need to use an ssh key to avoid password prompt
         - from local (if None)
        Compress and upload the directory to the storagespace
        """
        """
        - rsync over ssh the source to $tmpdir/prefabstor/$plistname.   (from remote machine to local one)
        - create a plist like we do for aydostor or G8stor
        - do a self.exists ... to find which files are not on remote yet
        - create tar with all files which do not exist
            - aa/bb/...
            - compress each individual file using same compression as what we used for aydostor/g7stor (was something good)
        - upload tar to remote temp space
        - expand tar to required storage space
        - upload plist to storspace under plist/$plistname.plist (using file_upload)
            - metadataStorspace!=None then use other storspace for uploading the plist
        - remove tmpdir if removetmpdir=True
        """

        if not host:
            host = j.tools.executorLocal

        if host.type == 'ssh':
            source = '%s@%s:%s' % (host.login, host.addr, source)
            target = j.sal.fs.getTmpDirPath()
            j.sal.fs.copyDirTree(source, target, keepsymlinks=True, ssh=True, sshport=host.port)

        else:
            target = source

        # building the flist struct
        f = j.tools.flist.getFlist(target)
        f.add(target, excludes)

        # exists = self.exists(f.getHashList())
        # needed = []
        #
        # for key, exist in exists.items():
        #     files = f.filesFromHash(key)
        #
        #     # from a hash, all files will point to the same content
        #     # by checking only the first one from the filelist, we will know
        #     # if this this key point to regular file(s) or not
        #     #
        #     # if it's not found, we will only append one file
        #     # it's not needed to append each file, they contains all the same data
        #     if not exist and f.isRegular(files[0]):
        #         needed.append({'hash': key, 'file': files[0]})

        dirs = f.dirCollection.find()

        needed = [(os.path.join(target, d.dbobj.location), d.key) for d in dirs]
        if len(needed) == 0:
            # nothing to upload
            return True

        # 'needed' contains hashs and filenames needed to upload
        tmptar = '/tmp/jstor-upload.tar'
        tar = j.tools.tarfile.get(tmptar, j.tools.tarfile.WRITE)

        for file in needed:
            tar.addFiltered(file[0], file[1], self._clearFile)

        tar.close()

        # now, tar file is ready, let's upload it to the storage then extract it
        # setting the expire time to 1, this will ensure that the file will
        # be removed in the next check
        self.file_upload(tmptar, 'jstor-uploader.tar', expiration=1)
        self._extract('jstor-uploader.tar')

        # uploading the flist to the (right) store
        mds = self

        if metadataStorspace:
            mds = self.stor.getStorageSpace(metadataStorspace)

        flistpath = j.sal.fs.getTmpDirPath()
        flistfile = j.sal.fs.joinPaths(flistpath, flistname + '.flist')

        # dumping flist and uploading it
        j.sal.fs.writeFile(flistfile, f.dumps())
        mds.flist_upload(flistfile, '%s.flist' % flistname)

        # cleaning: removing tar file, flist dir, ...
        j.sal.fs.removeDirTree(flistpath)
        j.sal.fs.remove(tmptar)

        # cleaning temp directory (if asked and not the local one)
        if target != source:
            if removetmpdir:
                j.sal.fs.removeDirTree(target)

    def download(self, flistname, destination="/mnt/", removetmpdir=True, cacheStorspace=None, metadataStorspace=None):
        """
        - download plist on remote stor (use storspace.filedownload())
        - if cacheStorspace not None: check which files we already have in the cache (use cacheStorspace.exists)
        - create a bash or python file which has commands to get required files & put in tar on remote
        - download tar
        - if cacheStorspace!=None: upload each file to restore not in cache yet to cache
        - restore the files to $tmpdir/prefabstor/$plistname  (all files, from cache & from remote, as efficient as possible)
            - decompress each file
        - rsync over ssh $tmpdir/prefabstor/$plistname  to the prefab we are working on
        - remove tmpdir if removetmpdir=True
        """
        # FIXME:
        jstortmp = '/tmp/jstor-extracted'
        if not j.sal.fs.isDir(jstortmp):
            j.sal.fs.createDir(jstortmp)

        # downloading flist
        mds = self

        if metadataStorspace:
            mds = self.stor.getStorageSpace(metadataStorspace)

        workdir = j.sal.fs.getTmpDirPath()
        flistfile = j.sal.fs.joinPaths(workdir, flistname + '.flist')
        mds.flist_download('%s.flist' % flistname, flistfile)
        flist = j.tools.flist.load(flistfile)
        flist.parse(flistfile)

        # checking for cache

        # building tar
        tarfile = '%s.tar' % flistname
        tarpath = j.sal.fs.joinPaths(self.archivepath, tarfile)

        self.tarball(flist.getHashList(), tarpath)

        # downloading tar
        dstpath = j.sal.fs.joinPaths(workdir, tarfile)
        self.file_download(tarpath, dstpath)

        # loading tar and uncompressing it
        tar = j.tools.tarfile.get(dstpath, j.tools.tarfile.READ)

        if not j.sal.fs.isDir(jstortmp):
            j.sal.fs.createDir(jstortmp)

        tar.extract(jstortmp)

        # restoring permissions
        for key in flist.getHashList():
            file = j.sal.fs.joinPaths(jstortmp, self.hashPath(key))

            final = j.sal.fs.joinPaths(destination, flist.getPath(key)[1:])
            fpath = j.sal.fs.getDirName(final)

            if not j.sal.fs.isDir(fpath):
                j.sal.fs.createDir(fpath)

            if flist.isRegular(key):
                j.sal.fs.copyFile(file, final)
                j.sal.fs.chown(final, flist.getOwner(key), flist.getGroup(key))
                j.sal.fs.chmod(final, int(flist.getMode(key), 8))

            else:
                self.logger.info("FIXME, NOT REGULAR")

    def tarball(self, keys, target):
        script = self.stor.scripts.tarball(self.spacepath, keys, target)
        data = self.prefab.core.execute_python(script)
        return data

    def flist(self, path):
        """
        Generate a flist for the path contents
        """
        # TODO: maxim, the original format was not a dict, this is not ideal, if
        # you have a big directory this will explode ! it needs to go back to
        # original text format & processing on disk directly not in mem
        flist = {}
        for file in j.sal.fswalker.walk(path, recurse=True):
            stat = j.sal.fs.statPath(file)
            hash = j.data.hash.md5(file)
            mode = oct(stat.st_mode)[3:]

            flist[hash] = {
                'file': file,
                'size': stat.st_size,
                'mode': mode,
                'uname': pwd.getpwuid(stat.st_uid).pw_name,
                'gname': grp.getgrgid(stat.st_gid).gr_name
            }

        return flist

    def flistDumps(self, flist):
        data = []

        for key, f in flist.items():
            line = "%s|%s|%d|%s|%s|%s" % (
                f['file'], key, f['size'], f['uname'], f['gname'], f['mode']
            )

            data.append(line)

        return "\n".join(data) + "\n"

    def flistLoads(self, flist):
        data = {}

        for line in flist.splitlines():
            f = line.split('|')

            data[f[1]] = {
                'file': f[0],
                'size': int(f[2]),
                'mode': f[5],
                'uname': f[3],
                'gname': f[4]
            }

        return data

    def _extract(self, tarfile):
        """
        Extract a tarball on the storage, this should be used only internally
        """
        tarsource = j.sal.fs.joinPaths(self.spacepath, tarfile)
        tartarget = self.spacepath

        self.prefab.core.run('tar -xvf %s -C %s' % (tarsource, tartarget))
        self.prefab.core.file_unlink(tarsource)


"""
some remarks

- all upload/download use the prefab base classes (not the optionally enabled rsync or httpserver on the stor)

"""
