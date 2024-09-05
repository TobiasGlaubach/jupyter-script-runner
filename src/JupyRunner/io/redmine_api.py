import hashlib
import os, time, json

from JupyRunner.core import filesys_storage_api, schema, helpers

log = helpers.log

def _get_rm_info(pth):
    with open(pth, 'r') as fp:
        key = fp.read().strip()
    return key



server = ''
token = ''
redmine = None


def setup(config):
    global token, server, redmine
    try:
        
        import redminelib
        config = config.get('storage_locations', config)
        rm = config.get('redmine', config)

        api_key = _get_rm_info(rm.get('login'))
        url = rm.get('url')
        redmine = redminelib.Redmine(url, key=api_key)
        
        log.info('Sucessfully connected to redmine')
    except Exception as err:
        log.error(err)


def start(config):
    return RedmineAccessor(config)

class RedmineAccessor(object):
    def __init__(self, config) -> None:
        self.config = config
        
    def test_should_upload(self, datafile:schema.Datafile):
        if 'redmine' in self.config['storage_locations'] and datafile.file_path:
            raise NotImplementedError('can not upload to redmine, because this is not implemented yet!')
        else:
            return False
        

    def upload(self, datafile:schema.Datafile, file):
        assert datafile.file_path, 'LocalFile: can not upload, since no "source" is given'
        raise NotImplementedError()
    
        api = LocalFileAccessor(datafile.file_path)
        api.upload(file)
        datafile.data_json.update({'meta': api.get_meta()})
        return datafile 

    def destruct(self):
        pass