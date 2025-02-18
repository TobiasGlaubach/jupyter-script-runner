import datetime
import hashlib
import io
import os, time, json

from JupyRunner.core import filesys_storage_api, schema, helpers

log = helpers.log


server = ''
token = ''
redmine = None


def setup(config):
    global token, server, redmine
    try:
        assert os.environ.get('RM_URL'), 'no redmine server URL defined!'
        import redminelib
        config = config.get('storage_locations', config)
        # gets the API key from an environmental variable with the name LOGIN_INFO_RM
        api_key = os.environ.get('RM_LOGIN_INFO', '').strip()
        url = os.environ.get('RM_URL', '')
        redmine = redminelib.Redmine(url, key=api_key)
        
        log.info('Sucessfully connected to redmine')
    except Exception as err:
        log.error(err)


def start(config):

    try:
        return RedmineAccessor(config)    
    except AssertionError as err:
        log.error(err)
        return None
    
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

def upload_file2wiki(page_title, project_id, file_path):
    global redmine
    filename = os.path.basename(file_path)
    page = redmine.wiki_page.get(page_title, project_id=project_id, include=['attachments'])
    to_upload = [{"path" : file_path, "filename" : filename, "content_type" : "application/octet-stream"}]
    page.uploads = to_upload
    page.comments = f'updated at {datetime.datetime.utcnow().isoformat()}'
    page.save()

def upload_bytes2wiki(page_title, project_id, bytes_object, filename):
    global redmine
    page = redmine.wiki_page.get(page_title, project_id=project_id, include=['attachments'])
    to_upload = [{"path": io.BytesIO(bytes_object), "filename": filename, "content_type": "application/octet-stream"}]
    page.uploads = to_upload
    page.comments = f'updated at {datetime.datetime.utcnow().isoformat()}'
    page.save()