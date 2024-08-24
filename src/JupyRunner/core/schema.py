import enum, json

from typing import Optional
from sqlmodel import Field, SQLModel, Relationship, Enum, String, Column, JSON

from JupyRunner.core import helpers

STATUS_DICT = {
    "INITIALIZING": 0,
    "AWAITING_CHECK": 1,
    "WAITING_TO_RUN": 2,
    "HOLD": 3,
    "STARTING": 10,
    "RUNNING": 11,
    "CANCELLING": 12,
    "FINISHING": 13,
    "POST_PROCESSING": 14,
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


class STATUS(enum.IntEnum):
    """
    Status codes for the observations status
    """
    
    INITIALIZING = 0
    AWAITING_CHECK = 1
    WAITING_TO_RUN = 2
    HOLD = 3, 
    
    STARTING = 10
    RUNNING = 11
    CANCELLING = 12
    FINISHING = 13

    FINISHED = 101
    ABORTED = 102

    CANCELLED = 1001
    FAILED = 1000
    FAULTY = 1002

status_dc = {str(s.name): s.value for s in STATUS}


class STATUS_DATAFILE(enum.IntEnum):
    """
    Status codes for the observations status
    """
    INITIALIZED = 0
    AWAITING_MANUAL_UPLOAD = 2
    
    READY = 100
    FAULTY = 1002
    
    ERROR = 1003
    EMPTY = 2000

class DATAFILE_TYPE(enum.StrEnum):
    """
    Status codes for the datafile types "str", "dataframe", "binary"
    """

    TEXTFILE = "text"
    DATAFRAME = "dataframe"
    BINARY = "binary"
    

class Device(SQLModel, table=True):
    id: str = Field(primary_key=True, unique=True)
    address: str = Field(nullable=False)
    connection_protocol: str = Field(nullable=False)
    configuration: str = Field(nullable=True)
    comments: str = Field(nullable=True)
    params_json: Optional[dict] = Field(sa_column=Column(JSON))
    data_json: Optional[dict] = Field(sa_column=Column(JSON))
    last_change_time_iso: str = Field(nullable=False, default='{}')

class Script(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    script_name: str = Field(max_length=255, nullable=False)
    script_version: str = Field(max_length=255, nullable=False)
    script_in_path: str = Field(max_length=255, nullable=False)
    script_out_path: str = Field(max_length=255, nullable=False)

    device_id: str = Field(max_length=255, nullable=False, foreign_key="device.id")
    script_params_json: Optional[dict] = Field(sa_column=Column(JSON))

    start_condition: str = Field(nullable=True)
    end_condition: str = Field(nullable=True)

    time_initiated_iso: str = Field(nullable=False)
    time_started_iso: Optional[str] = Field(nullable=True)
    time_finished_iso: Optional[str] = Field(nullable=True)

    status: STATUS = Field(default=STATUS.INITIALIZING)
    errors: str = Field(nullable=True)
    comments: str = Field(nullable=True)

    forecasted_oc: str = Field(nullable=True)
    papermill_json: Optional[dict] = Field(sa_column=Column(JSON))

    data_json: Optional[dict] = Field(sa_column=Column(JSON))

    last_change_time_iso: str = Field(nullable=False, default='{}')

    # Relationship with the Device table (assuming you have a Device class defined)
    device: Device | None = Relationship(back_populates="scripts")


class DataFile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    script_id: int = Field(nullable=False, foreign_key="script.id")
    device_id: str = Field(max_length=255, nullable=False, foreign_key="device.id")
    tags: str = Field(nullable=True)
    meas_name: str = Field(max_length=255, nullable=False)
    status: STATUS_DATAFILE = Field(nullable=False)  # Consider using an enum for status
    errors: str = Field(nullable=True)
    data_type: DATAFILE_TYPE = Field(nullable=False)
    source: str = Field(nullable=True)
    data_json: Optional[dict] = Field(sa_column=Column(JSON))
    comments: str = Field(nullable=True)
    last_change_time_iso: str = Field(nullable=False)

    # Relationships with the Script and Device tables
    script: Script | None = Relationship(back_populates="datafiles")
    device: Device | None = Relationship(back_populates="datafiles")



class ProjectVariable(SQLModel, table=True):
    id: str = Field(primary_key=True, unique=True)
    value_json: Optional[dict] = Field(sa_column=Column(JSON))
    data_json: Optional[dict] = Field(sa_column=Column(JSON))
    last_change_time_iso: str = Field(nullable=False)

    