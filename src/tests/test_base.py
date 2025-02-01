import time
import pytest

from sqlmodel import Session, create_engine, SQLModel, select

import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
if __name__ == '__main__':
    # print(parent_dir)
    sys.path.insert(0, parent_dir)

config = {
    'db': {
        'filepath': 'test_database.db'
    },
    'globals': {
        'dbserver_uri': 'http://localhost:8000',
    },
    'pathes': {
        'default_dir_meas': '/home/jovyan/shared/meas/',
        'default_dir_repo': '/home/jovyan/shared/repo/',
        'default_dir_docs': '/home/jovyan/shared/meas/loose_docs/',
        'default_dir_libs': '/home/jovyan/shared/meas/libs/',
    }
}

import JupyRunner.core.schema
JupyRunner.core.schema.config.update(config)

config = JupyRunner.core.schema.config

from JupyRunner.core.schema import Device, Script  # Replace with your actual models
from JupyRunner.core.db_interface import add_to_db, setup, start, get_engine
from JupyRunner.core.helpers import get_utcnow
from JupyRunner.core import scriptrunner
import JupyRunner.core.filesys_storage_api as fs



fs.setup(config)
fs.start(config)


def test_set_script_out_path():

    meas = config.get('pathes').get('default_dir_meas')
    s = Script(id = 1, device_id='Rxstest', script_in_path='/home/jovyan/shared/repo/testing_script.ipynb')
    s.set_script_out_path()

    assert s.script_out_path
    assert s.script_out_path.startswith(meas)
    assert fs.default_dir_data.startswith(meas)



def test_get_data_dir():

    meas = config.get('pathes').get('default_dir_meas')
    s = Script(id = 1, device_id='Rxstest', script_in_path='/home/jovyan/shared/repo/testing_script.ipynb')
    s.set_script_out_path()
    d = s.get_data_dir()

    assert d
    assert d.startswith(meas)
    assert d.startswith(s.get_script_dir()), f'{d=} not startswith {s.get_script_dir()=}'


    print(d)

def test_get_url_full():
    s = Script(id=1, device_id='Rxstest', script_in_path='/home/jovyan/shared/repo/testing_script.ipynb', script_out_path='/home/jovyan/shared/meas/testing_script.ipynb')
    expected_url = f'http://localhost:8000/script/1'
    assert s.get_url_full() == expected_url

def test_get_link_md():
    s = Script(id=1, device_id='Rxstest', script_in_path='/home/jovyan/shared/repo/testing_script.ipynb', script_out_path='/home/jovyan/shared/meas/testing_script.ipynb')
    expected_s = '[script_1](http://localhost:8000/script/1)'
    assert s.get_link_md() == expected_s

def test_get_showpath_md():
    outp = '/home/jovyan/shared/meas/testing_script.ipynb'
    s = Script(id=1, device_id='Rxstest', script_in_path='/home/jovyan/shared/repo/testing_script.ipynb', script_out_path=outp)
    expected_s = f'[testing_script](http://localhost:8000/show/{outp})'
    assert s.get_showpath_md() == expected_s

    
if __name__ == '__main__':
    pytest.main([__file__])

