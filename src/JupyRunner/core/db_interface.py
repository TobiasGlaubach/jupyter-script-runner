

from sqlmodel import Session, create_engine, SQLModel, select
from JupyRunner.core import schema


engine = None
sqlite_file_name = None
sqlite_file_name = None


def setup(config):
    global engine, sqlite_url, sqlite_file_name
    sqlite_file_name = config.get('db', {})['filepath']
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    connect_args = {"check_same_thread": False}
    engine = create_engine(sqlite_url, echo=True, connect_args=connect_args)

def start(config):
    SQLModel.metadata.create_all(engine)
    
def add(obj):
    with Session(engine) as session:
        session.add(obj)
        session.commit()
        session.refresh(obj)
        return obj

def create(obj):
    return add(obj)

def get(data_type:type, obj_id:int|str):
    with Session(engine) as session:
        return session.get(data_type, obj_id)
    
def get_all(data_type:type):
    with Session(engine) as session:
        return session.exec(select(data_type)).all()

def get_n(data_type:type, n_max:int):
    with Session(engine) as session:
        return session.exec(select(data_type)).fetchmany(n_max)

