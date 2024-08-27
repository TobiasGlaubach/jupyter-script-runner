

import datetime, json
from sqlmodel import Session, create_engine, SQLModel, select
from JupyRunner.core import schema, helpers

log = helpers.log

engine = None
sqlite_file_name = None



def json_serializer(obj):
    return json.dumps(obj, ensure_ascii=False, default=schema.json_serial)

def json_deserializer(obj):
    return _json_deserializer(json.loads(obj))

def _json_deserializer(dc):
    if isinstance(dc, dict):
        return {k:_json_deserializer(d) for k, d in dc.items()}
    elif isinstance(dc, list):
        return [_json_deserializer(d) for d in dc]
    elif isinstance(dc, str) and dc.endswith('Z') and helpers.match_zulutime(dc):
        return helpers.parse_zulutime(dc)
    else:
        return dc

def setup(config):
    global engine, sqlite_url, sqlite_file_name
    sqlite_file_name = config.get('db', {})['filepath']
    sqlite_url = f"sqlite:///{sqlite_file_name}"
    connect_args = {"check_same_thread": False}
    engine = create_engine(sqlite_url, echo=True, connect_args=connect_args, json_serializer=json_serializer, json_deserializer=json_deserializer)

def start(config):
    helpers.log.info(f"creating all tables for {sqlite_file_name=}")
    SQLModel.metadata.create_all(engine)
    commit(schema.ProjectVariable(id='dbi_info', data_json={'t_last': helpers.get_utcnow(), 'info': helpers.get_sys_info()}))
    

def get_engine():
    global engine
    return engine

def add_to_db(session, obj):
    obj.last_time_changed = helpers.get_utcnow()
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def set_property(data_type:type, obj_id, **kwargs):
    with Session(engine) as session:
        obj = session.get(data_type, obj_id)
        if not obj:
            raise KeyError(f'the object id {obj_id=} for {data_type=} was not found on the server')
        for key, v in kwargs.items():
            if not hasattr(obj, key):
                raise KeyError(f'the object id {obj_id=} for {data_type=} does not have the property {key=}, which supposed to be set')
            setattr(obj, key, v)
        return add_to_db(session, obj)


def commit(obj):
    with Session(engine) as session:
        existing_model = session.get(type(obj), obj.id)
        
        if existing_model:
            # Update existing model
            for attr, value in obj.model_dump().items():
                setattr(existing_model, attr, value)
        else:
            # Add new model
            return add_to_db(session, obj)
            
def add_many(objs):
    with Session(engine) as session:
        for obj in objs:
            obj.last_time_changed = helpers.get_utcnow()
            session.add(obj)

        session.commit()
        for obj in objs:
            session.refresh(obj)
        return objs
    
def se():
    return Session(engine)

def mwith():
    with Session(engine) as session:
        yield session
        
def get(data_type:type, obj_id:int|str):
    with Session(engine) as session:
        return session.get(data_type, obj_id)
    
def get_all(data_type:type):
    with Session(engine) as session:
        return session.exec(select(data_type)).all()

def get_n(data_type:type, n_max:int):
    with Session(engine) as session:
        q = select(data_type)
        if n_max > 0:
            q.limit(n_max)
        return session.exec(q).all()

def qry_scripts(t_min:datetime.datetime|None=None, 
                t_max:datetime.datetime|None=None, 
                stati:schema.STATUS|None=None,
                script_name:str='',
                script_version:str='',
                out_path:str='',
                n_max:int=-1, skipn:int=0, 
                ret_query = False
                ):
    with Session(engine) as session:
        s = schema.Script
        q = select(s).order_by(s.start_condition.asc())
        if t_min:
            q = q.where(s.start_condition >= t_min)
        if t_max:
            q = q.where(s.start_condition <= t_max)
        if stati:
            q = q.where(s.status.in_(stati))
        if script_name:
            q = q.where(s.script_name.like(f"%{script_name}%"))
        if script_version:
            q = q.where(s.script_version.like(f"%{script_version}%"))
        if out_path:
            q = q.where(s.out_path.like(f"%{out_path}%"))
        if skipn:
            q = q.offset(skipn)
        if n_max > 0:
            q = q.limit(n_max)
        
        if ret_query:
            return session.exec(q).all(), q
        else:
            return session.exec(q).all()
    


def get_ids(data_type:type, n_max:int=-1):
    with Session(engine) as session:
        q = select(data_type.id)
        if n_max > 0:
            q.limit(n_max)
        return session.exec(q).all()
    
def qry_tabledata(t_min, t_max, skipn, n_max, **kwargs):

    scripts, q = qry_scripts(n_max=n_max, skipn=skipn, t_min=t_min, t_max=t_max, ret_query=True, **kwargs)

    # df = pd.DataFrame.from_records(data)
    # columns=df.columns.tolist()
    log.debug(len(scripts))
    rows = [script.model_dump() for script in scripts if scripts]

    for row in rows:

        dc = row['datafiles']
        row['files'] = str(len(dc)) if hasattr(dc, "__len__") else "NO" + ' files'
        for k in row.keys():
            if ('condition' in k or 'time' in k) and row[k] and isinstance(row[k], str):
                row[k] = row[k].replace('T', ' ')

    columns = 'device_id id script_params_json status script_out_path files start_condition end_condition comments time_finished_iso script_name script_version'.split()
    rows = [[row.get(c, None) for c in columns] for row in scripts]

    inp = dict(n=n_max, skip=skipn, start_date=t_min, end_date=t_max)
    return dict(input=inp, queries=str(q), columns=columns, data=rows)
