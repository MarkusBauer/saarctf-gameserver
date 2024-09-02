"""
Files/folders represented in database.

A folder can be packed in a "package" and stored in the DB.
Each package has an identifier for it's content - two folders with the same content have the same package id.
Files in a package are identified by their MD5 hash.

Packages can't be updated, but they do deduplication of content. Only new or changed files will be stored / retrieved.

Large file storage (LFS): When loading a package, large files are stored in a seperate directory and symlink'ed to their destination.
If a large file is contained in multiple packages, it requires disk space only once.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Tuple, List

from controlserver.models import CheckerFilesystem, CheckerFile, db_session


class DBFilesystem:
    ignore_patterns = [
        re.compile(r'^__pycache__$'),
        re.compile(r'\.pyc$'),
        re.compile(r'^\.idea$'),
        re.compile(r'^\.git'),
        re.compile(r'^\.mypy_cache$'),
        re.compile(r'^gamelib$')
    ]

    def is_ignored(self, foldername: str) -> bool:
        for pattern in DBFilesystem.ignore_patterns:
            if pattern.match(foldername):
                return True
        return False

    def move_folder_to_package(self, folder: str) -> Tuple[str, bool]:
        """
        Upload a folder into a (possibly new) package.
        :param folder:
        :return: (package, is_new)
        """
        filesystem: List[CheckerFilesystem] = []  # for the db
        file_information = []  # for hash calculation
        for root, subdirs, files in os.walk(folder, followlinks=True):
            # add directories
            subdirs[:] = [dir for dir in subdirs if not self.is_ignored(dir)]
            for dir in subdirs:
                path = dir if root == folder else root[len(folder) + 1:] + '/' + dir
                filesystem.append(CheckerFilesystem(path=path))
                file_information.append([path, 'dir'])

            # add files
            for file in files:
                if self.is_ignored(file):
                    continue
                fname = root + '/' + file
                path = file if root == folder else root[len(folder) + 1:] + '/' + file
                hash = self.store_file_in_database(fname)
                filesystem.append(CheckerFilesystem(path=path, file_hash=hash))
                file_information.append([path, hash])

        file_information.sort(key=lambda x: x[0])
        package = hashlib.md5(json.dumps(file_information).encode('utf8')).hexdigest()
        # package already exists?
        if CheckerFilesystem.query.filter(CheckerFilesystem.package == package).count() > 0:
            return (package, False)
        # new package
        for fs in filesystem:
            fs.package = package
        session = db_session()
        session.add_all(filesystem)
        session.commit()
        return (package, True)

    def move_single_file_to_package(self, fname: str) -> Tuple[str, bool]:
        """
        Upload a package containing a single file in its root
        :param fname:
        :return: (package, is_new)
        """
        filesystem: List[CheckerFilesystem] = []  # for the db
        file_information = []  # for hash calculation
        # add files
        path = os.path.basename(fname)
        hash = self.store_file_in_database(fname)
        filesystem.append(CheckerFilesystem(path=path, file_hash=hash))
        file_information.append([path, hash])

        file_information.sort(key=lambda x: x[0])
        package = hashlib.md5(json.dumps(file_information).encode('utf8')).hexdigest()
        # package already exists?
        if CheckerFilesystem.query.filter(CheckerFilesystem.package == package).count() > 0:
            return (package, False)
        # new package
        for fs in filesystem:
            fs.package = package
        session = db_session()
        session.add_all(filesystem)
        session.commit()
        return (package, True)

    def store_file_in_database(self, fname: str) -> str:
        """
        Move a file into the database (if it's not already there)
        :param fname:
        :return: the md5 hash of the file
        """
        with open(fname, 'rb') as f:
            data = f.read()
        hash = hashlib.md5(data).hexdigest()
        if CheckerFile.query.filter(CheckerFile.file_hash == hash).count() == 0:
            session = db_session()
            session.add(CheckerFile(file_hash=hash, content=data))
            session.commit()
            print('Stored {} as {} in db'.format(fname, hash))
        return hash

    def load_package_to_folder(self, package: str, folder: Path, lfs_path: Path | None = None) -> bool:
        """
        Load a package from DB and copy its content to a folder
        :param package:
        :param folder:
        :param lfs_path: (optional) folder to store/locate large files
        :return: True if the package has been loaded, False otherwise (for example: already exists)
        """
        if folder.exists():
            return False
        base = Path(str(folder) + '.tmp')
        base.mkdir(exist_ok=True, parents=True)
        if lfs_path:
            lfs_path.mkdir(exist_ok=True, parents=True)
        filesystem: List[CheckerFilesystem] = CheckerFilesystem.query.filter(CheckerFilesystem.package == package)\
            .order_by(CheckerFilesystem.path).all()
        for fs in filesystem:
            if fs.file_hash:
                # Check if file in LFS
                if lfs_path and os.path.exists(lfs_path / fs.file_hash):
                    os.symlink(lfs_path / fs.file_hash, base / fs.path)
                else:
                    file: CheckerFile = CheckerFile.query.filter(CheckerFile.file_hash == fs.file_hash).one()
                    if lfs_path and len(file.content) > 500000:
                        # write to LFS
                        with open(lfs_path / fs.file_hash, 'wb') as f:
                            f.write(file.content)
                        os.symlink(lfs_path / fs.file_hash, base / fs.path)
                        os.chmod(lfs_path / fs.file_hash, 0o400)
                    else:
                        with open(base / fs.path, 'wb') as f:
                            f.write(file.content)
            else:
                os.makedirs(base / fs.path, exist_ok=True)
        os.rename(base, folder)
        return True
