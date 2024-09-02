"""
DB Filesystem loader.

Loads file/folder structures from the database, replicates them on disk, and loads python modules from these folders.
Details about the DB filesystem structure are in controlserver/db_filesystem.py
"""

import importlib.util
import sys
from types import ModuleType
from typing import Dict

from filelock import FileLock

from controlserver.db_filesystem import DBFilesystem
from saarctf_commons.config import config

sys.path.append(str(config.CHECKER_PACKAGES_PATH))


class PackageLoader:
    config.CHECKER_PACKAGES_PATH.mkdir(exist_ok=True)
    lock = FileLock(config.CHECKER_PACKAGES_PATH / '.lock')
    cached_modules: Dict[str, ModuleType] = {}

    @classmethod
    def package_exists(cls, package: str) -> bool:
        """
        :param package:
        :return: True if the package is already loaded
        """
        return (config.CHECKER_PACKAGES_PATH / package).exists()

    @classmethod
    def ensure_package_exists(cls, package: str) -> bool:
        """
        Load a package if it does not exist.
        :param package:
        :return: True if the package has been loaded, False if it already existed.
        """
        if cls.package_exists(package):
            return False
        with cls.lock:
            # check again now that we have the lock
            if cls.package_exists(package):
                return False
            DBFilesystem().load_package_to_folder(package, config.CHECKER_PACKAGES_PATH / package, config.CHECKER_PACKAGES_LFS)
            print('Package {} loaded'.format(package))
        return True

    @classmethod
    def load_module_from_package(cls, package: str, filename: str) -> ModuleType:
        """
        Import a python module from a package (loaded on the fly). Performs caching.
        :param package:
        :param filename: the filename relative to the package root
        :return:
        """
        # Read cache
        modulename = '{}.{}'.format(package, filename.replace('.py', '').replace('/', '.'))
        if modulename in cls.cached_modules:
            return cls.cached_modules[modulename]

        # Import module
        cls.ensure_package_exists(package)
        spec = importlib.util.spec_from_file_location(modulename, config.CHECKER_PACKAGES_PATH / package / filename)
        if spec is None:
            raise Exception('Spec/Loader is not present')
        module = importlib.util.module_from_spec(spec)
        if spec.loader is None:
            raise Exception('Loader is not present')
        spec.loader.exec_module(module)  # type: ignore
        print('PackageLoader imported {}'.format(modulename))

        # Write cache
        cls.cached_modules[modulename] = module
        return module
