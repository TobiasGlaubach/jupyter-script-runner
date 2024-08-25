
import datetime
from typing import Any, Dict
import requests

from sqlmodel import Session, create_engine, SQLModel, select
from JupyRunner.core import schema, helpers




config = None
url = None

def setup(cnfg):
    global config, url
    config = cnfg
    url = config['globals']['url']
    

def start(cnfg):
    global config
    config = cnfg

# def set_prop_remote(script: schema.Script):



class APIClient:
    def __init__(self, base_url:str=None):
        self.base_url = url if base_url is None else base_url

    def get(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}".rstrip('/')
        response = requests.get(url, params=params)
        response.raise_for_status() 
        return response.json()
        
    def post(self, endpoint, data=None):
        url = f"{self.base_url}/{endpoint}".rstrip('/')
        response = requests.post(url, json=data)
        response.raise_for_status()  # Raise an exception for error responses
        return response.json()

    def patch(self, endpoint, data:Dict[str, Any]|None=None):
        url = f"{self.base_url}/{endpoint}".rstrip('/')
        response = requests.patch(url, json=data)
        response.raise_for_status()  # Raise an exception for error responses
        return response.json()
    
class ModelClient(APIClient):
    def __init__(self, cls:schema.Script|schema.Device|schema.Datafile|schema.ProjectVariable, base_url:str=None):
        self.cls = cls
        self.clss = cls.__tablename__
        self._base_url = url if base_url is None else base_url

    @property
    def route(self):
        return self.cls.__tablename__

    @property
    def base_url(self):
        return f'{self._base_url}/{self.route}'
    
    def get(self, object_id):
        return self.cls(**super().get(str(object_id)))
    
    def get_all(self):
        return [self.cls(**kwargs) for kwargs in super().get('')]
    
    def post(self, data=None):
        if not isinstance(data, dict):
            data = data.model_dump()
        return super().post('', data)
    
    def put(self, data=None):
        if not isinstance(data, dict):
            data = data.model_dump()
        return super().put(data['id'], data)
    
    def patch(self, object_id, data: Dict[str, Any] | None = None):
        return super().patch(object_id, data)
    
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
                ):
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
        return response.json()
    
    
class DeviceClient(ModelClient):
    def __init__(self, base_url: str = None):
        super().__init__(schema.Device, base_url=base_url)

class DataFileClient(ModelClient):
    def __init__(self, base_url: str = None):
        super().__init__(schema.Datafile, base_url=base_url)

class ProjectVariableClient(ModelClient):
    def __init__(self, base_url: str = None):
        super().__init__(schema.ProjectVariable, base_url=base_url)