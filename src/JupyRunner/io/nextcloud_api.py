import asyncio
import hashlib
import os, time, json
import nextcloud_client
import xmltodict
from urllib import parse

import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(os.path.dirname(current_dir))
if __name__ == '__main__':
    print(parent_dir)
    sys.path.insert(0, parent_dir)

from JupyRunner.core import filesys_storage_api, schema, helpers

log = helpers.log

up = None
nc = None


def get_nc_info(login_info_file):
    from cryptography.fernet import Fernet

    with open(login_info_file, 'r') as fp:
        k, a, b = fp.readlines()
        FERNET = Fernet(bytes(k, 'ASCII'))
        a = FERNET.decrypt(a).decode()
        b = FERNET.decrypt(b).decode()
    return (a,b)

def setup(config):
    pass

def start(config):
    return NextcloudAccessor(config)


def _get_fileid_for_path(s, baseurl, url):
    

    log.debug('Nextcloud Loading {}'.format(url))

    req_data = """<d:propfind  xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns" xmlns:nc="http://nextcloud.org/ns">
    <d:prop>
        <oc:fileid />
    </d:prop>
    </d:propfind>"""

    response = s.request('PROPFIND', baseurl+url, data=req_data)
    response.raise_for_status()
    # dc = p.json()
    txt = response.text
    dc = xmltodict.parse(txt)
    r = dc['d:multistatus']['d:response']

    # print(response)
    assert isinstance(r, dict), f'received more than one responses for "{baseurl+url}"'
    # print('\n'*10)
    # print(r)
    # print('\n'*10)
    return r.get('d:propstat', {}).get('d:prop', {}).get('oc:fileid', '0')



class NextcloudAccessor(object):
    def __init__(self, config) -> None:
        self.config = config

        
        assert self.mycnfg, 'no login info given for nextcloud!'

        global up, nc
        if up is None:
            up = get_nc_info(self.mycnfg['login'])

        if nc is None:
            nc = nextcloud_client.Client(self.mycnfg['url'])
            nc.login(*up)
        
        self.up = up
        self.nc = nc

    @property
    def mycnfg(self):
        return self.config.get('storage_locations', {}).get('nextcloud')
    
    @property
    def default_dir(self):
        return self.mycnfg.get('kwargs', {}).get('default_dir', '')
    
    @property
    def baseurl(self):
        return self.nc.url

    def get_file_link(self, remote_path):
        fileid = self.get_file_id(remote_path)
        return '{}/index.php/f/{}'.format(self.baseurl.rstrip('/'), fileid) if fileid else ''

    def get_file_id(self, remote_path):
        p1 = f'/remote.php/dav/files/{self.up[0]}'
        url = p1 + parse.quote(remote_path.encode('utf-8'))
        fid = _get_fileid_for_path(self.nc._session, self.baseurl, url)
        log.debug(f'received {fid=} for {remote_path} @{self.baseurl=}')
        fidi = int(fid)
        assert fidi, f'egtting file id for {remote_path} @{self.baseurl=} failed with {fid=}'
        return fidi

        
    def mk_full_path(self, path):
        if self.default_dir:
            return self.default_dir.rstrip('/') + '/' + path.lstrip('/')
    
    def test_exists(self, remote_path):
        try:
            return self.nc.file_info(remote_path)
        except nextcloud_client.nextcloud_client.HTTPResponseError:
            return {}

    def test_should_upload(self, datafile:schema.Datafile):
        if 'nextcloud' in self.config['storage_locations'] and datafile.file_path:
            path = self.mk_full_path(datafile.file_path)
            return filesys_storage_api.is_pathname_valid(path)
        return False
        
    async def upload(self, datafile:schema.Datafile, file:bytes):
        return self._upload(datafile, file)
    
        # if self.mycnfg.get('run_async'):
        #     loop = asyncio.get_running_loop()
        #     return await loop.run_in_executor(None, self._upload(datafile, file))
        # else:
        #     return self._upload(datafile, file)
    
    def mkdirs(self, d):
        if '/' in d and d != '/':
            ds = os.path.dirname(d)
            log.info(f'making sub dir: "{ds}"')
            self.mkdirs(ds)
        if d == '/':
            return
        
        direxists = True
        try:
            res = self.nc.file_info(d)
            direxists = res is not None           
        except nextcloud_client.nextcloud_client.HTTPResponseError as err:
            if err.status_code == 404:
                direxists = False
            else:
                raise  

        if not direxists:
            log.info(f'making dir: "{d}"')
            self.nc.mkdir(d)

    def upload_file_content(self, remote_path:str, file:bytes):
        
        log.info(f'upload_NC: -> {remote_path} on {self.nc.url}')
        
        if self.test_exists(remote_path):
            raise FileExistsError(f'file "{remote_path}" already exists @{self.baseurl}. Use update instead of upload!')
    
        dn = os.path.dirname(remote_path)
        self.mkdirs(dn)

        log.info(f'upload_NC:  -> uploading()')
        try:
            res = self.nc.put_file_contents(remote_path, file)            
        except nextcloud_client.nextcloud_client.HTTPResponseError as err:
            if err.status_code == 405 and 'exist' in err.res.text:
                raise FileExistsError(err.res.text)
            else:
                raise err

        assert res, f'upload failed for: -> {remote_path} on {self.nc.url}'

    def _upload(self, datafile:schema.Datafile, file:bytes):
        
        assert self.test_should_upload(datafile), 'NextcloudAccessor: can not upload, since test_should_upload failed!'
        
        remote_path = self.mk_full_path(datafile.file_path)
        
        self.upload_file_content(remote_path, file)

        link_url = self.get_file_link(remote_path)
        info = self.nc.file_info(remote_path)
        # share = self.nc.get_shares(remote_path)

        # print('\n'*10)
        # print(link_url)
        # print(info)
        # print(share)
        # print('\n'*10)

        if datafile.locations_storage_json is None:
            datafile.locations_storage_json = {}

        if not 'nextcloud' in datafile.locations_storage_json:
            datafile.locations_storage_json['nextcloud'] = {}
        if info:
            datafile.locations_storage_json['nextcloud'].update({'meta': info.attributes, 'full_path': remote_path, 'link': link_url})

        return datafile

    def destruct(self):
        pass

if __name__ == '__main__':
    
    import yaml, time
    p = r'C:\Users\tglaubach\repos\jupyter-script-runner\src\config.yaml'
    with open(p, 'r') as fp:
        config = yaml.safe_load(fp)


    api = start(config)

    o = api._upload(schema.Datafile(id=1, file_path=f'/testdir/{time.time_ns()}_testfile.txt'), f'tnow = {time.time()} some test data!'.encode())

    print(o.model_dump())
    
