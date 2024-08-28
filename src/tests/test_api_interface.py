import time
import pytest
import requests

import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
if __name__ == '__main__':
    print(parent_dir)
    sys.path.insert(0, parent_dir)


import JupyRunner.core.api_interface as api
from JupyRunner.core.helpers import get_utcnow
from JupyRunner.core import schema


def test_create_device_and_script():

    config = {'db': {
        'filepath': 'test_database.db'
        },
        'globals': {
            'dbserver_uri': 'http://localhost:8000', 
            'default_dir_repo': 'scripts/'
        }
    }

    api.setup(config)
    api.start(config)

    before = get_utcnow()

    r = requests.get(api.url.rstrip('/') + '/ping')
    assert r.status_code == 200, f'no api running at {api.url=}'
    assert 'JupyRunner'.lower() in r.text.lower(), f'api running at {api.url=} doesnt seem to be a JupyRunner api'


    device_id = f"test_{time.time_ns()}"
    new_obj = api.DeviceClient().post({"id":device_id})
    assert new_obj
    assert new_obj.id
    assert new_obj.id == device_id
    assert new_obj.last_time_changed > before

    new_obj = api.DeviceClient().get(device_id)
    assert new_obj
    assert new_obj.id
    assert new_obj.id == device_id
    assert new_obj.last_time_changed > before

    # Generate a test script for the device
    dc = {
        'device_id': device_id,
        "script_in_path": "path/to/test_script.ipynb",
        # ... other script attributes
    }

    new_obj = api.ScriptClient().post(dc)
    assert new_obj
    assert new_obj.id
    assert new_obj.id > 0
    assert new_obj.last_time_changed > before


    new_obj = api.ScriptClient().get(new_obj.id)
    assert new_obj
    assert new_obj.id
    assert new_obj.id > 0


    # Verify that both device and script exist in the database
    new_obj2 = api.ScriptClient().get(new_obj.id)
    assert new_obj2 is not None
    assert new_obj2.device_id == device_id
    assert new_obj2

    after = get_utcnow()

    assert new_obj2.time_initiated > before
    assert new_obj2.time_initiated < after

    assert new_obj2.start_condition > before
    assert new_obj2.start_condition < after

    assert new_obj2.last_time_changed > before
    assert new_obj2.last_time_changed < after

    assert new_obj2.end_condition > after
    assert new_obj2.end_condition > new_obj2.start_condition

    
def test_projectvariable_api_basic():
    
    a = api.ProjectVariableClient('http://localhost:7990')
    assert a.clss == schema.ProjectVariable.__tablename__
    assert a.cls is schema.ProjectVariable


def test_put_script():

    config = {'db': {
        'filepath': 'test_database.db'
        },
        'globals': {
            'dbserver_uri': 'http://localhost:8000', 
            'default_dir_repo': 'scripts/'
        }
    }

    api.setup(config)
    api.start(config)

    before = get_utcnow()

    r = requests.get(api.url.rstrip('/') + '/ping')
    assert r.status_code == 200, f'no api running at {api.url=}'
    assert 'JupyRunner'.lower() in r.text.lower(), f'api running at {api.url=} doesnt seem to be a JupyRunner api'



    # Generate a test script for the device
    dc = {
        "script_in_path": "path/to/test_script.ipynb",
        # ... other script attributes
    }

    new_obj = api.ScriptClient().post(dc)
    assert new_obj
    assert new_obj.id
    assert new_obj.id > 0
    assert new_obj.last_time_changed > before


    new_obj.status = schema.STATUS.FAULTY
    new_obj = api.ScriptClient().put(new_obj)
    assert new_obj
    assert new_obj.id
    assert new_obj.status == schema.STATUS.FAULTY


    # Verify that both device and script exist in the database
    new_obj2 = api.ScriptClient().get(new_obj.id)
    assert new_obj2 is not None
    assert new_obj2.id == new_obj.id
    assert new_obj2.status == schema.STATUS.FAULTY

    after = get_utcnow()

    assert new_obj2.time_initiated > before
    assert new_obj2.time_initiated < after

    assert new_obj2.start_condition > before
    assert new_obj2.start_condition < after

    assert new_obj2.last_time_changed > before
    assert new_obj2.last_time_changed < after

    assert new_obj2.end_condition > after
    assert new_obj2.end_condition > new_obj2.start_condition


if __name__ == '__main__':
    # test_projectvariable_api_basic()
    pytest.main([__file__])