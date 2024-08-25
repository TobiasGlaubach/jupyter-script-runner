

import hashlib
import os, time, json


from JupyRunner.core import filesys_storage_api, schema, helpers

log = helpers.log

def setup(config):
    pass

def start(config):
    return LocalFile(config)

class LocalFile(object):
    def __init__(self, config) -> None:
        self.config = config

    def test_source_matches(self, datafile:schema.Datafile):
        return filesys_storage_api.is_pathname_valid(datafile.source)

    def upload(self, datafile:schema.Datafile, file):
        assert datafile.source, 'LocalFile: can not upload, since no "source" is given'

        api = LocalFileAccessor(datafile.source)
        api.upload(file)
        datafile.data_json.update({'meta': api.get_meta()})
        return datafile 
    
    def destruct(self):
        pass


class LocalFileAccessor(object):
    @staticmethod
    def test_valid(p):
        return os.path.exists(p)
    
    def __init__(self, p) -> None:
        self.p = p
    
    def info(self):
        return f'Local File with Path="{self.p}'
    
    def get_meta(self, *args, **kwargs):
        stat = os.stat(self.p)
        return {
            'size': stat.st_size,
            'created': time.ctime(stat.st_ctime),
            'modified': time.ctime(stat.st_mtime),
            'accessed': time.ctime(stat.st_atime)
        }


    def get_data_version_id(self, meta= {}, algorithm='sha256'):
        """Calculates the checksum of a file using the specified algorithm.

        Args:
            filename: The path to the file.
            algorithm: The name of the hash algorithm to use (e.g., 'sha256', 'md5').

        Returns:
            The hexadecimal representation of the checksum.
        """

        with open(self.p, 'rb') as f:
            hash_obj = hashlib.new(algorithm)
            while True:
                chunk = f.read(1024)
                if not chunk:
                    break
                hash_obj.update(chunk)
            return hash_obj.hexdigest()

    def load(self) -> bytes:
        with open(self.p, 'rb') as fp:
            return fp.read()
  
    def upload(self, content:bytes):
        with open(self.p, 'wb') as fp:
            fp.write(content)

