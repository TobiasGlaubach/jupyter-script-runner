

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

    def mk_full_path(self, path):
        dir = self.config['storage_locations'].get('local', None)
        dir = filesys_storage_api.default_dir_data if not dir else dir
        return os.path.join(dir, path).replace('\\', '/')
    
    def test_exists(self, path):
        if os.path.exists(path):
            return LocalFileAccessor(path).get_meta()
        else:
            return {}

    def test_should_upload(self, datafile:schema.Datafile):
        if 'local' in self.config['storage_locations']:
            path = self.mk_full_path(datafile.file_path)
            return filesys_storage_api.is_pathname_valid(path)
        return False

    async def upload(self, datafile:schema.Datafile, file:bytes):
        assert self.test_should_upload(datafile), f'ERROR: "test_should_upload" failed before upload to {self}'
        path = self.mk_full_path(self.config.get('local', datafile.file_path))
        log.info(f'upload_local: saving data to: {path}')
           
        if self.test_exists(path):
            raise FileExistsError(f'file "{path}" already exists @local_filesystem. Use update instead of upload!')
        
        api = LocalFileAccessor(path)
        api.upload(file)

        if datafile.locations_storage_json is None:
            datafile.locations_storage_json = {}

        if not 'local' in datafile.locations_storage_json:
            datafile.locations_storage_json['local'] = {}

        datafile.locations_storage_json['local'].update({'meta': api.get_meta(), 'full_path': path})

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
        if not os.path.exists(os.path.dirname(self.p)):
            os.makedirs(os.path.dirname(self.p))

        with open(self.p, 'wb') as fp:
            fp.write(content)

