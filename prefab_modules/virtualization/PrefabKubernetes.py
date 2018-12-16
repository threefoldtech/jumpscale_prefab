
import time
from Jumpscale import j

app = j.tools.prefab._getBaseAppClass()
OPENSSL = """
[ req ]
distinguished_name = req_distinguished_name
[req_distinguished_name]
[ v3_ca ]
basicConstraints = critical, CA:TRUE
keyUsage = critical, digitalSignature, keyEncipherment, keyCertSign
[ v3_req_etcd ]
basicConstraints = CA:FALSE
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = @alt_names_etcd
[ alt_names_etcd ]
{alt_names_etcd}
"""

ETCD_SERVICE = """
[Unit]
Description=etcd
Documentation=https://github.com/coreos

[Service]
ExecStart={DIR_BIN}/etcd \\
  --name {name} \\
  --cert-file=$CFGDIR/etcd/pki/etcd.crt \\
  --key-file=$CFGDIR/etcd/pki/etcd.key \\
  --peer-cert-file=$CFGDIR/etcd/pki/etcd-peer.crt \\
  --peer-key-file=$CFGDIR/etcd/pki/etcd-peer.key \\
  --trusted-ca-file=$CFGDIR/etcd/pki/etcd-ca.crt \\
  --peer-trusted-ca-file=$CFGDIR/etcd/pki/etcd-ca.crt \\
  --peer-client-cert-auth \\
  --client-cert-auth \\
  --initial-advertise-peer-urls https://{node_ip}:2380 \\
  --listen-peer-urls https://{node_ip}:2380 \\
  --listen-client-urls https://{node_ip}:2379,http://127.0.0.1:2379 \\
  --advertise-client-urls https://{node_ip}:2379 \\
  --initial-cluster-token etcd-cluster-0 \\
  --initial-cluster {initial_cluster} \\
  --data-dir=/var/lib/etcd
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

KUBE_INIT = """
apiVersion: kubeadm.k8s.io/v1alpha1
kind: MasterConfiguration
api:
  advertiseAddress: {node_ip}
  bindPort: 6443
authorizationMode: Node,RBAC
kubernetesVersion: 1.8.5
etcd:
  endpoints:
{endpoints}
  caFile: $CFGDIR/etcd/pki/etcd-ca.crt
  certFile: $CFGDIR/etcd/pki/etcd.crt
  keyFile: $CFGDIR/etcd/pki/etcd.key
  dataDir: /var/lib/etcd
  etcdVersion: v3.2.9
networking:
  podSubnet: {flannel_subnet}
  serviceSubnet: {service_subnet}
apiServerCertSANs:
{external_ips}

certificatesDir: /etc/kubernetes/pki/
"""


class PrefabKubernetes(app):
    """
    Prefab that allows deployment of kubernetes cluster or adding new nodes to an existing cluster
    """
    NAME = "kubectl"

    def multihost_install(self, masters, nodes=None, external_ips=None, skip_flight_checks=False,
                          service_subnet='10.96.0.0/16', reset=False, install_binaries=True):
        """
        Important !! only supports centos, fedora and ubuntu 1604
        Use a list of prefab connections where all nodes need to be reachable from all other nodes or at least from the master node.
        this installer will:
        - deploy/generate required secrets/keys to allow user to access this kubernetes
        - make sure that dashboard is installed as well on kubernetes
        - use /storage inside the node (make sure is btrfs partition?) as the backend for kubernetes
        - deploy zerotier network (optional) into the node which connects to the kubernetes (as pub network?)

        :param masters: required list of masters prefabs connection
        :param nodes: list of workers prefab connection, if not given, we assume masters can run workload
        :param external_ips: list(str) list of extra ips to add to certs
        :param unsafe: bool will allow pods to be created on master nodes.
        :param skip_flight_checks: bool skip preflight checks from kubeadm.
        :param service_subnet: str cidr to use for the services in kubernets .
        :param reset: rerun the code even if it has been run again. this may not be safe (used for development only)
        :param install_binaries: if True will call install_binaries before configuring nodes

        :return (dict(), str): return the kubelet config as a dict write as yaml file to any kubectl that need to control the cluster

        """
        if self.doneCheck("multihost_install", reset):
            return

        if nodes is None:
            nodes = []
        if external_ips is None:
            external_ips = []

        external_ips = [master.executor.sshclient.addr for master in masters] + external_ips
        if install_binaries:
            self.install_binaries(masters)
        self.setup_etcd_certs(masters)
        self.install_etcd_cluster(masters)
        unsafe = len(nodes) == 0  # allow work load to run on masters
        join_line, config = self.install_kube_masters(masters, external_ips=external_ips, service_subnet=service_subnet,
                                                      skip_flight_checks=skip_flight_checks,
                                                      unsafe=unsafe, reset=reset)
        for node in nodes:
            node.virtualization.kubernetes.install_minion(join_line)


        self.doneSet("multihost_install")

        return config, join_line

    def install_dependencies(self, reset=False):
        """
        Installs required libs and packages for the cluster to run.

        @param reset ,,if True will resintall even if the code has been run before.
        """
        if self.doneCheck("install_dependencies", reset):
            return

        # install requirement for the running kubernetes basics
        self.prefab.system.package.mdupdate(reset=True)
        self.prefab.system.package.install('openssl,mercurial,conntrack,ntp,curl,apt-transport-https')
        # self.prefab.runtimes.golang.install()
        self.prefab.virtualization.docker.install(branch='17.03')

        # required for bridge manipulation in ubuntu
        if self.prefab.core.isUbuntu:
            self.prefab.system.package.install('bridge-utils')

        self.doneSet("install_dependencies")

    def install_base(self, reset=False):
        """
        Builds the kubernetes binaries and Moves them to the appropriate location

        @param reset,, bool will default to false, if ture  will rebuild even if the code has been run before.
        """
        if self.doneCheck("install_base", reset):
            return

        if not self.prefab.core.isUbuntu:
            raise RuntimeError(
                'Only ubuntu systems are supported at the moment.')

        self.install_dependencies()
        script_content = """
        apt-get update && apt-get install -y apt-transport-https
        curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | apt-key add -
        cat <<EOF >/etc/apt/sources.list.d/kubernetes.list
        deb http://apt.kubernetes.io/ kubernetes-xenial main
        """
        self.prefab.core.run(script_content, showout=False)
        self.prefab.system.package.mdupdate(reset=True)
        self.prefab.system.package.install('kubelet=1.8.5-00,kubeadm=1.8.5-00')
        self.install_kube_client(reset, '/usr/local/bin/kubectl')

        # build
        self.doneSet("install_base")

    def install_kube_client(self, reset=False, location='{DIR_BIN}/kubectl'):
        """
        Installs kubectl. Supported platformers are: macOS and Linux.
        @param reset,, bool will default to false, if ture  will rebuild even if the code has been run before.
        @param location,, string download file destination.
        """
        if self.doneCheck("install_kube_client", reset):
            return
        url = 'https://storage.googleapis.com/kubernetes-release/release/v1.8.5/bin/{}/amd64/kubectl'
        if self.prefab.core.isMac:
            url = url.format('darwin')
        elif self.prefab.core.isLinux:
            url = url.format('linux')
        self.prefab.core.run('curl -L {url} -o {loc}'.format(url=url, loc=location), showout=False)
        self.prefab.core.file_attribs(location, mode='+x')
        self.doneSet("install_kube_client")

    def setup_etcd_certs(self, nodes, save=False):
        """
        Generate the  kubernets ssl certificates and etcd certifactes to be use by the cluster.
        it is recommended that this method run on a ceprate node that will be controlling the cluster so that
        the certificates will already be there.

        @param nodes,, list(prefab) list of master node prefab connections
        """
        self.prefab.core.dir_remove('{DIR_TEMP}/k8s')
        self.prefab.core.dir_ensure(
            '{DIR_TEMP}/k8s/crt {DIR_TEMP}/k8s/key {DIR_TEMP}/k8s/csr')
        # get node ips from prefab
        nodes_ip = [node.executor.sshclient.addr for node in nodes]

        # format ssl config to add these node ips and dns names to them
        alt_names_etcd = '\n'.join(['IP.{i} = {ip}'.format(i=i, ip=ip) for i, ip in enumerate(nodes_ip)])
        alt_names_etcd += '\n' + '\n'.join(['DNS.{i} = {hostname}'.format(i=i,
                                                                          hostname=node.core.hostname) for i, node in enumerate(nodes)])
        ssl_config = OPENSSL.format(alt_names_etcd=alt_names_etcd)

        # generate certigicates and sign them for use by etcd
        self.prefab.core.file_write('{DIR_TEMP}/k8s/openssl.cnf', ssl_config)
        cmd = """
        openssl genrsa -out {DIR_TEMP}/k8s/key/etcd-ca.key 4096
        openssl req -x509 -new -sha256 -nodes -key {DIR_TEMP}/k8s/key/etcd-ca.key -days 3650 -out {DIR_TEMP}/k8s/crt/etcd-ca.crt -subj '/CN=etcd-ca' -extensions v3_ca -config {DIR_TEMP}/k8s/openssl.cnf
        openssl genrsa -out {DIR_TEMP}/k8s/key/etcd.key 4096
        openssl req -new -sha256 -key {DIR_TEMP}/k8s/key/etcd.key -subj '/CN=etcd' -out {DIR_TEMP}/k8s/csr/etcd.csr
        openssl x509 -req -in {DIR_TEMP}/k8s/csr/etcd.csr -sha256 -CA {DIR_TEMP}/k8s/crt/etcd-ca.crt -CAkey {DIR_TEMP}/k8s/key/etcd-ca.key -CAcreateserial -out {DIR_TEMP}/k8s/crt/etcd.crt -days 365 -extensions v3_req_etcd -extfile {DIR_TEMP}/k8s/openssl.cnf
        openssl genrsa -out {DIR_TEMP}/k8s/key/etcd-peer.key 4096
        openssl req -new -sha256 -key {DIR_TEMP}/k8s/key/etcd-peer.key -subj '/CN=etcd-peer' -out {DIR_TEMP}/k8s/csr/etcd-peer.csr
        openssl x509 -req -in {DIR_TEMP}/k8s/csr/etcd-peer.csr -sha256 -CA {DIR_TEMP}/k8s/crt/etcd-ca.crt -CAkey {DIR_TEMP}/k8s/key/etcd-ca.key -CAcreateserial -out {DIR_TEMP}/k8s/crt/etcd-peer.crt -days 365 -extensions v3_req_etcd -extfile {DIR_TEMP}/k8s/openssl.cnf
        """
        self.prefab.core.run(cmd, showout=False)
        if save:
            self.prefab.core.file_copy('{DIR_TEMP}/k8s', '{DIR_HOME}/')

    def copy_etcd_certs(self, controller_node):
        """
        Copies the etcd certiftes from {DIR_TEMP}/k8s/ to the controller node to the current node. This assumes certs
        are created in the specified location.

        @param controller_node ,, object(prefab) prefab connection to the controller node which deploys the cluster should have ssh access to all nodes.
        """
        _, user, _ = controller_node.core.run('whoami', showout=False)
        controller_node.system.ssh.define_host(self.prefab.executor.sshclient.addr, user)
        tmp_key = j.sal.fs.getTmpFilePath()

        # we do this to avoid asking for passpharse interactively
        controller_node.core.file_copy(
            self.prefab.executor.sshclient.sshkey.path,
            tmp_key
        )

        passphrase = self.prefab.executor.sshclient.sshkey.passphrase

        code, _, _ = controller_node.core.run(
            'ssh-keygen -p -P "%s" -N "" -f %s' % (passphrase, tmp_key),
            showout=False
        )
        if code != 0:
            raise RuntimeError('failed to decrypt key')

        cmd = """
        scp -P {port} -i {key} {DIR_TEMP}/k8s/crt/etcd* {node_ip}:{cfg_dir}/etcd/pki/
        scp -P {port} -i {key} {DIR_TEMP}/k8s/key/etcd* {node_ip}:{cfg_dir}/etcd/pki/
        """.format(
            node_ip=self.prefab.executor.sshclient.addr,
            cfg_dir=self.prefab.executor.dir_paths['CFGDIR'],
            port=self.prefab.executor.sshclient.port or 22,
            key=tmp_key
        )

        controller_node.core.execute_bash(cmd)
        controller_node.core.file_unlink(tmp_key)

    def get_etcd_binaries(self, version='3.2.9'):
        """
        Download etcd tar with the specified version extract the binaries place them and the certs in the appropriate location.

        @param version ,, str numbered version of etcd to install.
        """
        etcd_ver = version if version.startswith('v') else 'v%s' % version
        cmd = """
        cd {DIR_TEMP}/etcd_{etcd_ver}
        curl -L {google_url}/{etcd_ver}/etcd-{etcd_ver}-linux-amd64.tar.gz -o etcd-{etcd_ver}-linux-amd64.tar.gz
        tar xzvf etcd-{etcd_ver}-linux-amd64.tar.gz -C .
        """.format(google_url='https://storage.googleapis.com/etcd', etcd_ver=etcd_ver,
                   github_url='https://github.com/coreos/etcd/releases/download')
        self.prefab.core.dir_ensure('{DIR_TEMP}/etcd_{etcd_ver}'.format(etcd_ver=etcd_ver))
        self.prefab.core.run(cmd, showout=False)
        self.prefab.core.dir_ensure('{DIR_BIN}')
        self.prefab.core.file_copy('{DIR_TEMP}/etcd_{etcd_ver}/etcd-{etcd_ver}-linux-amd64/etcd'.format(etcd_ver=etcd_ver),
                                   '{DIR_BIN}/etcd')
        self.prefab.core.file_copy('{DIR_TEMP}/etcd_{etcd_ver}/etcd-{etcd_ver}-linux-amd64/etcdctl'.format(etcd_ver=etcd_ver),
                                   '{DIR_BIN}/etcdctl')
        self.prefab.core.dir_remove("$CFGDIR/etcd/pki")
        self.prefab.core.dir_remove("/var/lib/etcd")
        self.prefab.core.dir_ensure('$CFGDIR/etcd/pki /var/lib/etcd')

    def install_binaries(self, nodes):
        for node in nodes:
            node.virtualization.kubernetes.get_etcd_binaries()
            node.virtualization.kubernetes.install_base()

    def install_etcd_cluster(self, nodes):
        """
        This installs etcd binaries and sets up the etcd cluster.

        @param nodes,, list(prefab) list of master node prefabs
        """

        nodes_ip = [node.executor.sshclient.addr for node in nodes]
        initial_cluster = ['%s=https://%s:2380' % (node.core.hostname, node.executor.sshclient.addr) for node in nodes]
        initial_cluster = ','.join(initial_cluster)
        for index, node in enumerate(nodes):
            pm = node.system.processmanager.get('systemd')
            node.virtualization.kubernetes.copy_etcd_certs(self.prefab)
            etcd_service = ETCD_SERVICE.format(*nodes_ip, name=node.core.hostname, node_ip=node.executor.sshclient.addr,
                                               initial_cluster=initial_cluster)

            node.core.file_write('/etc/systemd/system/etcd.service', etcd_service, replaceInContent=True)
            pm.reload()
            pm.restart('etcd')

    def wait_on_apiserver(self):
        """
        Wait for the api to restart
        """
        timer = 0
        while not self.prefab.system.process.tcpport_check(6443):
            time.sleep(1)
            timer += 1
            if timer > 30:
                return

    def install_kube_masters(self, nodes, external_ips, kube_cidr='10.0.0.0/16', service_subnet='10.96.0.0/16',
                             flannel=True, dashboard=False, unsafe=False, skip_flight_checks=False, reset=False):
        """
        Used to install kubernetes on master nodes configuring the flannel module and creating the certs
        will also optionally install dashboard

        @param nodes,, list(prefab) list of master node prefabs
        @param kube_cidr,,str Depending on what third-party provider you choose, you might have to set the --pod-network-cidr to something provider-specific.
        @param service_subnet,, str cidr range for the kubernetes range.
        @param flannel,,bool  if true install and configure flannel
        @param dashboard,,bool install and configure dashboard(could not expose on OVC).
        @param external_ips,,list(str) list of extra ips to add to certs.
        @param unsafe,, bool will allow pods to be created on master nodes.
        """
        if self.doneCheck("install_master", reset):
            return

        if flannel:
            kube_cidr = '10.244.0.0/16'

        # format docs and command with ips and names
        nodes_ip = [node.executor.sshclient.addr for node in nodes]
        init_node = nodes[0]
        cmd = 'kubeadm init --config %s/kubeadm-init.yaml' % (
            init_node.executor.dir_paths['HOMEDIR'])
        endpoints = ''.join(['  - https://%s:2379\n' % ip for ip in nodes_ip])
        dns_names = [node.core.hostname for node in nodes]
        external_ips = j.data.serializers.yaml.dumps(external_ips + dns_names)
        kube_init_yaml = KUBE_INIT.format(node_ip=nodes_ip[0], flannel_subnet=kube_cidr, endpoints=endpoints,
                                          service_subnet=service_subnet, external_ips=external_ips)

        # write config and run command
        init_node.core.file_write('%s/kubeadm-init.yaml' % init_node.executor.dir_paths['HOMEDIR'],
                                  kube_init_yaml, replaceInContent=True)
        if skip_flight_checks:
            cmd += ' --skip-preflight-checks'
        rc, out, err = init_node.core.run(cmd, showout=False)
        if rc != 0:
            raise RuntimeError(err)
        for line in reversed(out.splitlines()):
            if line.startswith('  kubeadm join --token'):
                join_line = line
                break

        # exchange keys to allow for ssh and scp from the init node to the other
        pub_key = init_node.core.file_read(init_node.system.ssh.keygen()).strip()
        for node in nodes[1:]:
            node.executor.sshclient.ssh_authorize('root', pubkey=pub_key)
            _, user, _ = init_node.core.run('whoami', showout=False)
            init_node.system.ssh.define_host(node.executor.sshclient.addr, user)


        # move the config to be able to use kubectl directly
        init_node.core.dir_ensure('{DIR_HOME}/.kube')
        init_node.core.file_copy('/etc/kubernetes/admin.conf', '{DIR_HOME}/.kube/config')
        if flannel:
            init_node.core.run(
                'kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/v0.9.0/Documentation/kube-flannel.yml',
                showout=False
            )

        if dashboard:
            init_node.core.run(
                'kubectl apply -f https://raw.githubusercontent.com/kubernetes/dashboard/master/src/deploy/recommended/kubernetes-dashboard.yaml',
                showout=False
            )

        log_message = """
        please wait until kube-dns deplyments are deployed before joining new nodes to the cluster.
        to check this use 'kubectl get pods --all-namepspaces'
        then pass the join line returned string to the install_minion
        """
        print(log_message)

        # remove node constriction for APISERVER
        pm = init_node.system.processmanager.get('systemd')
        pm.stop('kubelet')
        dockers_names = init_node.virtualization.docker.list_containers_names()
        for name in dockers_names:
            if 'apiserver' in name:
                init_node.core.run('docker stop %s' % name, showout=False)
                break
        init_node.core.run(
            'sed -i.bak "s/NodeRestriction//g" /etc/kubernetes/manifests/kube-apiserver.yaml',
            showout=False
        )
        pm.start('kubelet')
        init_node.core.run('docker start %s' % name, showout=False)

        init_node.virtualization.kubernetes.wait_on_apiserver()

        edit_cmd = """
        cd /etc/kubernetes
        sed -i.bak "s/kub01/{my_hostname}/g" /etc/kubernetes/*.conf
        sed -i.bak "s/{init_ip}/{node_ip}/g" /etc/kubernetes/*.conf
        sed -i.bak "s/advertise-address={init_ip}/advertise-address={node_ip}/g" /etc/kubernetes/manifests/kube-apiserver.yaml
        """
        send_cmd = """
        eval `ssh-agent -s`
        ssh-add /root/.ssh/default
        rsync -av -e ssh --progress /etc/kubernetes {master}:/etc/
        """
        node_json = {
            "metadata": {
                "labels": {
                    "node-role.kubernetes.io/master": ""
                }
            },
            "spec": {
                "taints": [{
                    "effect": "NoSchedule",
                    "key": "node-role.kubernetes.io/master",
                    "timeAdded": None
                }]
            }
        }
        system_node_config = {
            "apiVersion": "rbac.authorization.k8s.io/v1beta1",
            "kind": "ClusterRoleBinding",
            "metadata": {
                "name": "system:node"
            },
            "subjects": [{
                "kind": "Group",
                "name": "system:nodes"
            }]
        }
        init_node.core.file_write('{DIR_TEMP}/system_node_config.yaml', j.data.serializers.yaml.dumps(system_node_config))

        if unsafe:
            # if unsafe  comppletly remove role master from the cluster
            init_node.core.run(
                'kubectl taint nodes %s node-role.kubernetes.io/master-' % init_node.core.hostname,
                showout=False
            )
        else:
            # write patch file used later on to register the nodes as masters
            init_node.core.file_write('{DIR_TEMP}/master.yaml', j.data.serializers.yaml.dumps(node_json))

        for index, master in enumerate(nodes[1:]):
            # send certs from init node to the rest of the master nodes
            init_node.core.execute_bash(send_cmd.format(master=master.executor.sshclient.addr))
            # adjust the configs in the new nodes with the relative ip and hostname
            master.core.execute_bash(edit_cmd.format(node_ip=master.executor.sshclient.addr,
                                                     my_hostname=init_node.core.hostname,
                                                     init_ip=init_node.executor.sshclient.addr))

            pm = master.system.processmanager.get('systemd')
            pm.reload()
            pm.restart('kubelet')
            master.virtualization.kubernetes.wait_on_apiserver()
            master.core.dir_ensure('{DIR_HOME}/.kube')
            master.core.file_copy('/etc/kubernetes/admin.conf', '{DIR_HOME}/.kube/config')

            # giving time for the nodes to be registered
            for i in range(30):
                _, nodes_result, _ = init_node.core.run(
                    'kubectl get nodes',
                    showout=False
                )
                # checking if number of lines is equal to number of nodes to check if they are registered
                if len(nodes_result.splitlines()) - 1 == index + 2:
                    break

            if not unsafe:
                # else setting the nodes as master
                register_cmd = """kubectl patch node %s -p "$(cat {DIR_TEMP}/master.yaml)"
                """ % (master.core.hostname)
                init_node.core.execute_bash(register_cmd)

        # bind node users to system:node role
        patch_user_command = 'kubectl patch clusterrolebinding system:node -p "$(cat {DIR_TEMP}/system_node_config.yaml)"'
        init_node.core.execute_bash(patch_user_command)
        config = init_node.core.file_read('/etc/kubernetes/admin.conf')

        # build
        self.doneSet("install_master")

        return join_line, config

    def install_minion(self, join_line, reset=False, install_base=True):
        """
        Used to install the basic componenets of kubernetes on a minion node and make that node join the cluster
        specified in the join line param.

        @param join_line ,,str an output line produced when deploying a master node this is the return from install_master method.
        @param reset ,,bool bool will default to false, if ture  will rebuild even if the code has been run before.
        @param install_base ,, if True will install base
        """
        if self.doneCheck("install_minion", reset):
            return
        if install_base:
            self.install_base()
        self.prefab.core.run(join_line.strip(), showout=False)

        # build
        self.doneSet("install_minion")

    def generate_new_token(self, nodes):
        """
        TODO
        """
        pass
