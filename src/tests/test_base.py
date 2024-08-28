import time
import pytest

from sqlmodel import Session, create_engine, SQLModel, select

import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
if __name__ == '__main__':
    # print(parent_dir)
    sys.path.insert(0, parent_dir)


from JupyRunner.core.schema import Device, Script  # Replace with your actual models
from JupyRunner.core.db_interface import add_to_db, setup, start, get_engine
from JupyRunner.core.helpers import get_utcnow
from JupyRunner.core import scriptrunner
import JupyRunner.core.filesys_storage_api as fs

config = {
    'db': {
        'filepath': 'test_database.db'
    },
    'pathes': {
        'default_dir_meas': '/home/jovyan/shared/meas/',
        'default_dir_repo': '/home/jovyan/shared/repo/'
    }
}

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

    
if __name__ == '__main__':
    pytest.main([__file__])

