

import datetime, json
import os
import traceback
from sqlmodel import Session, create_engine, SQLModel, select
# from sqlalchemy.orm import select_related
from JupyRunner.core import schema, helpers


log = helpers.log

engine = None
sqlite_file_name = None



def json_serializer(obj):
    return json.dumps(obj, ensure_ascii=False, default=schema.json_serial)

def json_deserializer(obj):
    return _json_deserializer(json.loads(obj))


def _update_factory(key, expected_o, v):
    log.debug(f'_update_factory {key=} {type(expected_o)=}, {expected_o=}, {type(v)=} {v=}')
    if isinstance(v, type(expected_o)) or expected_o is None or type(expected_o) is None:
        return v
    elif isinstance(expected_o, datetime.datetime) and isinstance(v, str):
        dt = helpers.parse_zulutime(v)
        assert dt, f'failed to parse datetime string: {v}'
        return dt
    else:
        return type(expected_o)(v) # naively try constructing (should work for enum types!)

        



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
    helpers.log.info(f"Starting with DB location: {sqlite_file_name=} (can_write={os.access(sqlite_file_name, os.W_OK)})")

     
    
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
    is_existing = session.get(type(obj), obj.id)

    if not is_existing:
        session.add(obj)
    session.commit()

    return obj

def set_propert_sub(session, obj_type:type, obj_id, **kwargs):
    obj = session.get(obj_type, obj_id)
    if not obj:
        raise KeyError(f'the object id {obj_id=} for {obj_type=} was not found on the server')
    for key, v in kwargs.items():
        if not hasattr(obj, key):
            raise KeyError(f'the object id {obj_id=} for {obj_type=} does not have the property {key=}, which supposed to be set')
        kwargs[key] = _update_factory(key, getattr(obj, key), v)
    obj.sqlmodel_update(kwargs)
    obj.last_time_changed = helpers.get_utcnow()  # Update timestamp
    session.commit()
    session.refresh(obj)
    return obj
    

def set_property(obj_type:type, obj_id, **kwargs):
    with Session(engine) as session:
        return set_propert_sub(session, obj_type, obj_id, **kwargs)


def commit(obj):
    with Session(engine) as session:
        existing_model = session.get(type(obj), obj.id)

        if existing_model:
            
            kwargs = obj.model_dump(exclude_unset=True)
            log.debug(f'COMMIT existing with {kwargs=}')
            
            for key, v in kwargs.items():
                if not hasattr(obj, key):
                    raise KeyError(f'the object {obj} does not have the property {key=}, which supposed to be set')
                kwargs[key] = _update_factory(key, getattr(existing_model, key), v)

            existing_model.sqlmodel_update(kwargs)
            existing_model.last_time_changed = helpers.get_utcnow()  # Update timestamp

            session.add(existing_model)
            session.commit()
            session.refresh(existing_model)
            return existing_model

        else:
            # Add new model
            obj.last_time_changed = helpers.get_utcnow()
            proto = type(obj)()

            for key, v in obj.model_dump().items():
                if not hasattr(obj, key):
                    raise KeyError(f'the object {obj} does not have the property {key=}, which supposed to be set')
                vv = _update_factory(key, getattr(proto, key), getattr(obj, key))
                setattr(obj, key, vv)

            session.add(obj)
            session.commit()
            
            session.refresh(obj)
            log.debug(f'COMMIT NEW with {obj=}')
            return obj # session.get(type(obj), obj.id)
        

        

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
        # q = select(data_type).where(data_type.id == obj_id)
        # return session.exec(q.options(select_related(*data_type.__mapper__.relationships))).first()
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
                script_in_path:str='',
                script_version:str='',
                out_path:str='',
                n_max:int=-1, skipn:int=0, 
                ret_query = False
                ):
    with Session(engine) as session:
        return qry_scripts_sub(session, t_min, t_max, stati, script_name, script_in_path, script_version, out_path, n_max, skipn, ret_query)
    
def qry_scripts_sub(session, t_min:datetime.datetime|None=None, 
                t_max:datetime.datetime|None=None, 
                stati:schema.STATUS|None=None,
                script_name:str='',
                script_in_path:str='',
                script_version:str='',
                out_path:str='',
                n_max:int=-1, skipn:int=0, 
                ret_query = False):

    s = schema.Script
    q = select(s).order_by(s.start_condition.asc())
    if t_min:
        q = q.where(s.start_condition >= t_min)
    if t_max:
        q = q.where(s.start_condition <= t_max)
    if stati:
        q = q.where(s.status.in_(stati))
        # log.debug(f'{stati=}')
    if script_in_path:
        q = q.where(s.script_in_path.like(f"%{script_in_path}%"))
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

    log.debug('qry with:')
    log.debug(str(q))

    if ret_query:
        return session.exec(q).all(), q
    else:
        return session.exec(q).all()


def get_ids(data_type:type, n_max:int=-1, reqt_q = False):
    with Session(engine) as session:
        q = select(data_type.id)
        if n_max > 0:
            q.limit(n_max)
        res = session.exec(q).all()
        if reqt_q:
            return res, q
        else:
            return res
    
def qry_tabledata(t_min, t_max, skipn, n_max, **kwargs):
    with Session(engine) as session:
        scripts, q = qry_scripts(n_max=n_max, skipn=skipn, t_min=t_min, t_max=t_max, ret_query=True, **kwargs)

        # df = pd.DataFrame.from_records(data)
        # columns=df.columns.tolist()
        log.debug(len(scripts))
        rows = [{**script.model_dump(), **{'files': len(script.datafiles)}} for script in scripts if script]
        log.debug(rows)

        for row in rows:

            if not row['files']:
                row['files'] = "NO files"
            else:
                row['files'] = str(row['files']) + "  files"

            for k in row.keys():
                if isinstance(row[k], datetime.datetime):
                    row[k] = helpers.make_zulustr(row[k])

                if ('condition' in k or 'time' in k) and row[k] and isinstance(row[k], str):
                    row[k] = row[k].replace('T', ' ')
                    row[k] = row[k].split('.')[0]

                elif ('script_params_json' in k or '_json' in k) and row[k] and not isinstance(row[k], str):
                    row[k] = json.dumps(row[k], ensure_ascii=False, default=schema.json_serial)
                elif row[k] is None:
                    row[k] = ''

        columns = 'id device_id script_params_json status script_out_path files start_condition end_condition comments time_finished script_name script_version errors script_in_path'.split()
        rows = [[row.get(c, None) for c in columns] for row in rows]

        inp = dict(n=n_max, skip=skipn, start_date=t_min, end_date=t_max)
        return dict(input=inp, queries=str(q), columns=columns, data=list(reversed(rows)))
