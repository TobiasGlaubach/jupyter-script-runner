import hashlib
import os, time, json

from JupyRunner.core import filesys_storage_api, schema, helpers

log = helpers.log

def setup(config):
    pass

def start(config):
    return RedmineAccessor(config)

class RedmineAccessor(object):
    def __init__(self, config) -> None:
        self.config = config
        
    def test_source_matches(self, datafile:schema.Datafile):
        return filesys_storage_api.is_pathname_valid(datafile.source)

    def upload(self, datafile:schema.Datafile, file):
        assert datafile.source, 'LocalFile: can not upload, since no "source" is given'
        raise NotImplementedError()
    
        api = LocalFileAccessor(datafile.source)
        api.upload(file)
        datafile.data_json.update({'meta': api.get_meta()})
        return datafile 

    def destruct(self):
        pass