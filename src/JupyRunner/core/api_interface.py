
import datetime
import enum
from typing import Any, Dict
import requests

from sqlmodel import Session, create_engine, SQLModel, select
from JupyRunner.core import schema, helpers


log = helpers.log

config = None
url = None
client = None

def setup(cnfg):
    global config, url, client
    config = cnfg
    url = config['globals']['dbserver_uri']
    log.info(f'HTTP API initialized with {url=}')
    client = APIClient(url)    

def start(cnfg):
    global config
    config = cnfg

# def set_prop_remote(script: schema.Script):

def ping(_url = None):
    
    _url = url if not _url else _url
    assert _url, 'no URL given for ping!'
    _url = f"{_url.rstrip('/')}/ping"
    log.debug(f'GET: {_url}')

    response = requests.get(url)
    response.raise_for_status() 
    return response.text


class APIClient:
    def __init__(self, base_url:str=None, none_on_404 = False):
        self.base_url = url if base_url is None else base_url
        self.none_on_404 = none_on_404
    
    def _url(self, endpoint):
        return f"{self.base_url.rstrip('/')}/{str(endpoint).lstrip('/')}".rstrip('/')
    
    def _json(self, dc):
        if isinstance(dc, dict):
            return {k:self._json(d) for k, d in dc.items()}
        elif isinstance(dc, list):
            return [self._json(d) for d in dc]
        elif isinstance(dc, (datetime.datetime, datetime.date)):
            return helpers.make_zulustr(dc, remove_ms=False)
        elif isinstance(dc, (enum.IntEnum, enum.StrEnum, schema.STATUS, schema.STATUS_DATAFILE, schema.DATAFILE_TYPE)):
            return dc.name
        else:
            return dc

    def validate(self, inp, outp):
        for key, v in inp.items():
            assert key in outp, f'{key=} is missing in response! {outp=}'
            if key == 'last_time_changed':
                assert inp[key] < outp[key], f'last_time_changed <= before {inp[key]=} < {outp[key]=}'
            elif isinstance(inp[key], str) and isinstance(outp[key], str) and helpers.parse_zulutime(inp[key]) and helpers.parse_zulutime(outp[key]):
                vin, vout = inp[key], outp[key]
                vin = helpers.parse_zulutime(vin)
                vout = helpers.parse_zulutime(vout)
                assert vin == vout, f'{key=} was not updated! {vin=} != {vout=}'
            elif isinstance(inp[key], dict) and isinstance(outp[key], dict):
                pass # dont check for dict update
            else:
                assert inp[key] == outp[key], f'{key=} was not updated! {inp[key]=} != {outp[key]=}'
        return outp
    

        
    def get(self, endpoint, params=None):
        url = self._url(endpoint)
        log.debug(f'GET: {url} {params=}')
        response = requests.get(url, params=params) if params else requests.get(url)
        if response.status_code == 404 and self.none_on_404:
            return None
        
        response.raise_for_status() 
        return response.json()
        
    def put(self, endpoint, data=None):
        url = self._url(endpoint)
        data = self._json(data)
        log.debug(f'PUT: {url} {data=}')
        response = requests.put(url, json=data)
        response.raise_for_status()  # Raise an exception for error responses
        resp = response.json()
        self.validate(data, resp)
        return resp


    def post(self, endpoint, data=None):
        url = self._url(endpoint)
        data = self._json(data)
        log.debug(f'POST: {url} {data=}')
        response = requests.post(url, json=data)
        response.raise_for_status()  # Raise an exception for error responses
        resp = response.json()
        self.validate(data, resp)
        return resp
        

    def patch(self, endpoint, data:Dict[str, Any]|None=None):
        url = self._url(endpoint)
        data = self._json(data)
        log.debug(f'POST: {url} {data=}')
        response = requests.patch(url, json=data)
        response.raise_for_status()  # Raise an exception for error responses
        resp = response.json()
        self.validate(data, resp)
        return resp
    
class ModelClient(APIClient):
    def __init__(self, cls:schema.Script|schema.Device|schema.Datafile|schema.ProjectVariable, base_url:str=None):
        self.cls = cls
        self.clss = cls.__tablename__
        self._base_url = url if base_url is None else base_url
        self.none_on_404 = True

    @property
    def route(self):
        return self.cls.__tablename__

    @property
    def base_url(self):
        return f'{self._base_url}/{self.route}'
    
    def get(self, object_id):
        o = super().get(str(object_id))
        return None if o is None else self.cls.model_validate(o)
        
    def get_all(self):
        return [self.cls(**kwargs) for kwargs in super().get('')]
    
    def post(self, data=None):
        if not isinstance(data, dict):
            data = data.model_dump()
        return self.cls.model_validate(super().post('', data))
    
    def put(self, data=None):
        if not isinstance(data, dict):
            data = data.model_dump()
        return self.cls.model_validate(super().put(data['id'], data))
    
    def patch(self, object_id, data: Dict[str, Any] | None = None, **kwargs):
        if kwargs and not data:
            data = kwargs
        elif kwargs and data:
            data.update(kwargs)
        res = super().patch(object_id, data)
        log.debug(f'PATCH {object_id=} --> {res=}')
        return self.cls.model_validate(res)
    
class ScriptClient(ModelClient):
    def __init__(self, base_url: str = None):
        super().__init__(schema.Script, base_url=base_url)

    def qry(self, t_min:datetime.datetime|None=None, 
                t_max:datetime.datetime|None=None, 
                stati:schema.STATUS|None=None,
                script_name:str='',
                script_version:str='',
                out_path:str='',
                n_max:int=-1, skipn:int=0, 
                ) -> list[schema.Script]:
        kwargs = {
            "t_min": t_min,
            "t_max": t_max,
            "stati": stati,
            "script_name": script_name,
            "script_version": script_version,
            "out_path": out_path,
            "n_max": n_max,
            "skipn": skipn
        }

        url = f"{self._base_url}/qry/{self.route}".rstrip('/')
        response = requests.get(url, params=kwargs)
        response.raise_for_status() 
        return [self.cls.model_validate(v) for v in response.json()]
    

class DeviceClient(ModelClient):
    def __init__(self, base_url: str = None):
        super().__init__(schema.Device, base_url=base_url)

class DataFileClient(ModelClient):
    def __init__(self, base_url: str = None):
        super().__init__(schema.Datafile, base_url=base_url)

class ProjectVariableClient(ModelClient):
    def __init__(self, base_url: str = None):
        super().__init__(schema.ProjectVariable, base_url=base_url)