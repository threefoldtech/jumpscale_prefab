from setuptools import setup, find_packages
from setuptools.command.install import install as _install
from setuptools.command.develop import develop as _develop
import os


def _post_install(libname, libpath):
    from Jumpscale import j
    j.core.jsgenerator.generate()


class install(_install):

    def run(self):
        _install.run(self)
        libname = self.config_vars['dist_name']
        libpath = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), libname)
        self.execute(_post_install, (libname, libpath),
                     msg="Running post install task")


class develop(_develop):

    def run(self):
        _develop.run(self)
        libname = self.config_vars['dist_name']
        libpath = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), libname)
        self.execute(_post_install, (libname, libpath),
                     msg="Running post install task")


long_description = ""
try:
    from pypandoc import convert
    long_description = convert("README.md", 'rst')
except ImportError:
    long_description = ""


setup(
    name='JumpscalePrefab',
    version='9.5.1',
    description='Automation framework for cloud workloads remote sal, sal= system abstraction layer',
    long_description=long_description,
    url='https://github.com/Jumpscaler/prefab',
    author='ThreeFoldTech',
    author_email='info@threefold.tech',
    license='Apache',
    packages=find_packages(),
    install_requires=[
        'Jumpscale>=9.5.1',
        'paramiko>=2.2.3',  # for parallel-ssh
        'asyncssh>=1.9.0',
        'pymongo>=3.4.0',
    ],
    cmdclass={
        'install': install,
        'develop': develop,
        'developement': develop
    },
)
