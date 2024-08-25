import time
import pytest

from sqlmodel import Session, create_engine, SQLModel, select

import os, inspect, sys
current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parent_dir = os.path.dirname(current_dir)
if __name__ == '__main__':
    print(parent_dir)
    sys.path.insert(0, parent_dir)


from JupyRunner.core.schema import Device, Script  # Replace with your actual models
from JupyRunner.core.db_interface import add_to_db, setup, start, get_engine
from JupyRunner.core.helpers import get_utcnow
from JupyRunner.core import scriptrunner
import JupyRunner.core.filesys_storage_api as fs

@pytest.fixture(scope="session")
def engine():
    config = {'db': {
        'filepath': 'test_database.db'
        },
        'pathes': {
            'default_dir_meas': 'tests/test_data/',
            'default_dir_repo': 'scripts/'
        }
    }

    setup(config)
    start(config)
    fs.setup(config)
    fs.start(config)
    
    engine = get_engine()

    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)

@pytest.fixture(scope="function")
def session(engine):
    with Session(engine) as session:
        yield session

def test_create_device_and_script(session):
    before = get_utcnow()

    # Create a dummy device
    device_data = {
        "id": "test_device",
        # ... other device attributes
    }
    device = Device(**device_data)
    add_to_db(session, device)

    # Generate a test script for the device
    script_data = {
        "device_id": device.id,
        "script_in_path": "path/to/test_script.ipynb",
        # ... other script attributes
    }
    script = Script(**script_data)
    add_to_db(session, script)

    # Verify that both device and script exist in the database
    fetched_device = session.get(Device, device.id)
    assert fetched_device is not None
    assert fetched_device.id == device_data["id"]

    fetched_script = session.get(Script, script.id)
    assert fetched_script is not None
    assert fetched_script.id > 0
    assert fetched_script.device_id == device.id
    after = get_utcnow()

    assert fetched_script.time_initiated > before
    assert fetched_script.time_initiated < after

    assert fetched_script.start_condition > before
    assert fetched_script.start_condition < after

    assert fetched_script.last_time_changed > before
    assert fetched_script.last_time_changed < after

    assert fetched_script.end_condition > after
    assert fetched_script.end_condition > fetched_script.start_condition

    assert fetched_script



def test_re_check(session):
    before = get_utcnow()

    # Create a dummy device
    device_data = {
        "id": "test_device_{int(time.time_ns())}",
        # ... other device attributes
    }
    device = Device(**device_data)
    add_to_db(session, device)

    # Generate a test script for the device
    script_data = {
        "device_id": device.id,
        "script_in_path": "scripts/example_script.ipynb",
    }
    script = Script(**script_data)
    add_to_db(session, script)

    e = None
    try:
        scriptrunner.pre_check(script)
    except Exception as err:
        e = err

    assert e is None, str(e)

    


def test_run_script(session):
    before = get_utcnow()

    # Create a dummy device
    device_data = {
        "id": f"test_device_{int(time.time_ns())}",
        # ... other device attributes
    }
    device = Device(**device_data)
    add_to_db(session, device)

    # Generate a test script for the device
    script_data = {
        "device_id": device.id,
        "script_in_path": "scripts/example_script.ipynb",
    }
    script = Script(**script_data)
    add_to_db(session, script)
    scriptrunner.run_script(session, script)

if __name__ == '__main__':
    pytest.main()