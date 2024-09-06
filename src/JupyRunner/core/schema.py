import enum, json, datetime
import hashlib
import os
import re


from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship, Enum, String, Column, JSON

from JupyRunner.core import helpers
import JupyRunner.core.filesys_storage_api as filesys

STATUS_DICT = {
    "INITIALIZING": 0,
    "AWAITING_CHECK": 1,
    "WAITING_TO_RUN": 2,
    "HOLD": 3,
    "STARTING": 10,
    "RUNNING": 11,
    "CANCELLING": 12,
    "FINISHING": 13,
    "UPLOADING": 14,
    "AWAITING_POST_PROC": 100,
    "FINISHED": 101,
    "ABORTED": 102,
    "CANCELLED": 1001,
    "FAILED": 1000,
    "FAULTY": 1002,
    "POST_PROC_FAILED": 1003
}

STATUS_MEAS_DICT = {
    "INITIALIZED": 0,
    "READY": 100,
    "FAULTY": 1002,
    "ERROR": 1003,
    "EMPTY": 2000
}


class STATUS(enum.StrEnum):
    """
    Status codes for the observations status
    """
    
    INITIALIZING = "INITIALIZING"
    AWAITING_CHECK = "AWAITING_CHECK"
    WAITING_TO_RUN = "WAITING_TO_RUN"
    HOLD = "HOLD", 
    
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    UPLOADING = "UPLOADING"
    CANCELLING = "CANCELLING"
    FINISHING = "FINISHING"

    FINISHED = "FINISHED"
    ABORTED = "ABORTED"

    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    FAULTY = "FAULTY"

status_dc = {str(s.name): STATUS_DICT[s.name] for s in STATUS}

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime.datetime, datetime.date)):
        return helpers.make_zulustr(obj, remove_ms=False)
    elif isinstance(obj, (enum.IntEnum, enum.StrEnum, STATUS, STATUS_DATAFILE, DATAFILE_TYPE)):
        return obj.name


    raise TypeError (f"Type{type(obj)=} not serializable")



class STATUS_DATAFILE(enum.StrEnum):
    """
    Status codes for the observations status
    """
    INITIALIZED = "INITIALIZED"
    AWAITING_MANUAL_UPLOAD = "AWAITING_MANUAL_UPLOAD"
    
    READY = "READY"
    FAULTY = "FAULTY"
    
    ERROR = "ERROR"
    EMPTY = "EMPTY"

class DATAFILE_TYPE(enum.StrEnum):
    """
    Status codes for the datafile types "str", "dataframe", "binary"
    """

    UNKNOWN = "unknown"
    JSON = "json"
    TEXTFILE = "text"
    REPORT = "rep"
    DATAFRAME = "dataframe"
    BINARY = "binary"


class Device(SQLModel, table=True):
    id: str = Field(primary_key=True, unique=True, nullable=False)
    source: str = Field(default='', nullable=False)

    address: str = Field(default='', nullable=False)
    connection_protocol: str = Field(default='', nullable=False)
    configuration: str = Field(default='', nullable=False)
    comments: str = Field(default='', nullable=False)
    data_json: Optional[dict] = Field(sa_column=Column(JSON), default_factory= lambda : {})
    last_time_changed: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)

    scripts: list["Script"] = Relationship(back_populates="device", sa_relationship_kwargs={"lazy": "selectin"})
    datafiles: list["Datafile"] = Relationship(back_populates="device", sa_relationship_kwargs={"lazy": "selectin"})
    def append_error_msg(self, err):
        self.errors += '\n' + str(err)

def get_default_params():
    return {'follow_up_script' : {'script_in_path': '', 'script_params_json': {}}}

class Script(SQLModel, table=True):


    id: Optional[int] = Field(default=None, primary_key=True)
    script_name: str = Field(default='', max_length=255, nullable=False)
    script_version: str = Field(default='', max_length=255, nullable=False)
    script_in_path: str = Field(default='', max_length=255, nullable=False)
    script_out_path: str = Field(default='', max_length=255, nullable=False)

    default_data_dir: str = Field(default='', max_length=255, nullable=False)

    device_id:  str|None = Field(default=None, max_length=255, nullable=True, foreign_key="device.id")
    script_params_json: dict|None = Field(sa_column=Column(JSON), default_factory=get_default_params)

    start_condition: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)
    end_condition: datetime.datetime = Field(nullable=False, default_factory=lambda : helpers.get_utcnow() + datetime.timedelta(hours=7*24))

    time_initiated: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)
    time_started: Optional[datetime.datetime] = Field(nullable=True, default_factory=helpers.get_utcnow)
    time_finished: Optional[datetime.datetime] = Field(nullable=False, default_factory=helpers.get_utcnow)

    status: STATUS = Field(default=STATUS.INITIALIZING)
    errors: str = Field(default='', nullable=False)
    comments: str = Field(default='', nullable=False)

    docs_json: Optional[dict] = Field(sa_column=Column(JSON), default_factory=lambda: {})

    papermill_json: Optional[dict] = Field(sa_column=Column(JSON))
    data_json: Optional[dict] = Field(sa_column=Column(JSON), default_factory=lambda: {})

    last_time_changed: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)

    device: Device | None = Relationship(back_populates="scripts", sa_relationship_kwargs={"lazy": "selectin"})
    datafiles: list["Datafile"] = Relationship(back_populates="script", sa_relationship_kwargs={"lazy": "selectin"})

    def before_commit(self):
        assert self.id < 1725603466, f'{self.id=} are you trying to commit a timestamp to an id?'

    @staticmethod
    def construct(script_in_path, 
                  script_params_json:str|None=None, 
                  start_condition:datetime.datetime|None=None, 
                  end_condition:datetime.datetime|None=None,
                  device_id: str|None = None):

        assert script_in_path, 'need to give "script_in_path"!'

        script_name  = os.path.basename(script_in_path.split('.')[0])

        filename = os.path.basename(script_in_path)
        script_name, extension = os.path.splitext(filename)

        if start_condition is None:
            start_condition = helpers.get_utcnow()
        if end_condition is None:
            end_condition = start_condition + datetime.timedelta(hours=7*24)
        
        assert end_condition >= start_condition, f'end condition must be bigger than start condition {start_condition=} {end_condition=}'

        return Script(
            script_in_path=script_in_path,
            script_name = script_name,
            script_params_json=script_params_json,
            start_condition=start_condition,
            end_condition=end_condition,
            device_id = device_id
        )
    
    def get_data_dir(self):
        if self.default_data_dir:
            return self.default_data_dir
        else:
            return os.path.join(self.get_script_dir(), 'data').replace('\\', '/')
    
    def get_reports_dir(self):
        if self.default_data_dir:
            return self.default_data_dir
        else:
            return os.path.join(self.get_script_dir(), 'reports').replace('\\', '/')

    def get_script_dir(self):
        assert self.script_out_path, 'no "script_out_path" given yet to get a script folder from!'
        return os.path.dirname(self.script_out_path)
    
    def set_script_name(self, force_overwrite=False):
        if self.script_name and not force_overwrite:
            return self.script_name
        
        self.script_name = os.path.basename(self.script_in_path)
        return self.script_name
    
    def set_script_version(self, force_overwrite=False):
        if self.script_version and not force_overwrite:
            return self.script_version
        
        tlast_change = os.path.getmtime(self.script_in_path)
        dtlast_change = helpers.make_zulustr(datetime.datetime.fromtimestamp(tlast_change))
        with open(self.script_in_path,'rb') as f:
            self.script_version = hashlib.md5(f.read()).hexdigest() + '_' + dtlast_change
        return self.script_version
    

    def set_script_out_path(self, force_overwrite=False):
        # BUG: There is some form of bug here with the default script dir folder, but it seems to be working for now (somehow)!

        if self.script_out_path and not force_overwrite:
            return self.script_out_path
        
        assert self.id is not None, 'the script is not commited to the database yet, can not set the script out path!'
        assert self.time_started, 'can not set out_path, because the script has no "time_started" yet!'

        filename = os.path.basename(self.script_in_path)
        name, extension = os.path.splitext(filename) # BUG: I suspect this line. needs debugging

        if name.startswith('script_'): name = name[len('script_'):]
        if name.startswith('exp_'): name = name[len('exp_'):]
        if name.startswith('experiment_'): name = name[len('experiment_'):]
        if name.startswith('test_'): name = name[len('test_'):]
        if name.startswith('ana_'): name = name[len('ana_'):]
        if name.startswith('analysis_'): name = name[len('analysis_'):]
        if name.startswith('base_'): name = name[len('base_'):]

        device_id = self.device_id if self.device_id else 'no_device'
        script_id = self.id
        pth_out = filesys.get_script_save_filepath(self.time_started, script_id, device_id, name, make_dir=False)

        if not filesys.is_pathname_valid(pth_out):
            # handle windows style volume descriptors starting with C: or similar
            if re.match(r"(^[A-Za-z]:).+", pth_out):
                pth_out = pth_out[:2] + re.sub(r'[\n\\\*>:<?\"|\t]', '', pth_out[2:])
            else:
                pth_out = re.sub(r'[\n\\\*>:<?\"|\t]', '', pth_out)
        
        if not filesys.is_pathname_valid(pth_out):
            raise Exception('The out script file path is invalid. GOT: "' + pth_out + '"')

        pth_out = pth_out.strip()
        self.script_out_path = pth_out
        return self.script_out_path
    
    def append_error_msg(self, err):
        self.errors += '\n' + str(err)

    def test_for_start_condition(self):
        if self.start_condition:
            tstart = self.start_condition
            utcnow = helpers.get_utcnow()
            return utcnow >= tstart
        else:
            raise Exception(f'start_condition signature did not match expected')


class Datafile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    script_id: int = Field(nullable=False, foreign_key="script.id")
    device_id: str = Field(max_length=255, nullable=True, foreign_key="device.id")
    filename: str = Field(max_length=255, nullable=False, default="")

    tags: List[str] = Field(sa_column=Column(JSON), default_factory=lambda: [])
    meas_name: str = Field(max_length=255, nullable=False, default='')
    status: STATUS_DATAFILE = Field(nullable=False, default=STATUS_DATAFILE.INITIALIZED)
    errors: str = Field(default='', nullable=False)
    data_type: DATAFILE_TYPE = Field(default=DATAFILE_TYPE.UNKNOWN, nullable=False)
    mime_type: str = Field(default='', nullable=False)

    file_path: str = Field(nullable=False)
    locations_storage_json: Optional[dict] = Field(sa_column=Column(JSON), default_factory=lambda: {})
    data_json: Optional[dict] = Field(sa_column=Column(JSON), default_factory=lambda: {})
    comments: str = Field(default='', nullable=False)
    time_initiated: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)
    last_time_changed: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)

    # Relationships with the Script and Device tables
    script: Script | None = Relationship(back_populates="datafiles", sa_relationship_kwargs={"lazy": "selectin"})
    device: Device | None = Relationship(back_populates="datafiles", sa_relationship_kwargs={"lazy": "selectin"})

    def append_error_msg(self, err):
        self.errors += '\n' + str(err)


class ProjectVariable(SQLModel, table=True):
    id: str = Field(primary_key=True, unique=True)
    data_json: Optional[dict] = Field(sa_column=Column(JSON), default_factory=lambda: {})
    data_json: Optional[dict] = Field(sa_column=Column(JSON), default_factory=lambda: {})

    time_initiated: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)
    last_time_changed: datetime.datetime = Field(nullable=False, default_factory=helpers.get_utcnow)

    def append_error_msg(self, err):
        self.errors += '\n' + str(err)

schema_dc = {cls.__name__: cls.__tablename__ for cls in [Script, Datafile, ProjectVariable, Device]}
schema_cls_dc = {cls: cls.__tablename__ for cls in [Script, Datafile, ProjectVariable, Device]}
schema_cls_dc_inv = {v:k for k, v in schema_cls_dc.items()}
