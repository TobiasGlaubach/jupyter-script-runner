
from contextlib import asynccontextmanager
import datetime
import os
import subprocess
import time
import traceback
from typing import Any, Callable, Dict, List
import nbconvert

from fastapi import FastAPI, Form, HTTPException, Path, Query, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import FileResponse

from pydantic import BaseModel, Field
from jinja2 import Environment, FileSystemLoader


from JupyRunner.core import db_interface as dbi
from JupyRunner.core import schema, helpers, filesys_storage_api, helpers_mattermost, helpers_papermill, scriptrunner
from JupyRunner.io import nextcloud_api, redmine_api, local_filesys_api
import JupyRunner



import yaml

log = helpers.log

t_started = helpers.get_utcnow()
template_dir = ''
static_dir = ''

with open('config.yaml', 'r') as fp:
    config = yaml.safe_load(fp)

helpers.set_loglevel(config)

modules = [dbi, filesys_storage_api]
serializers = {
    'nextcloud': nextcloud_api,
    'redmine': redmine_api,
    'filesys': local_filesys_api,
}

for module in modules:
    module.setup(config)

for module in modules:
    module.start(config)

serializers = {k:v.start(config) for k, v in serializers.items()}

log.info('STARTED!')

app = FastAPI()
templates = Jinja2Templates(directory="templates")  # You can use this for more complex templates
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Environment(loader=FileSystemLoader("templates"))
app.mount("/data", StaticFiles(directory=filesys_storage_api.default_dir_data), name="data")  # Assuming a static directory
app.mount("/repos", StaticFiles(directory=filesys_storage_api.default_dir_repo), name="repos")  # Assuming a static directory

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global serializers

#     log.info('STARTED!')

#     yield

#     for k, v in serializers.items():
#         v.destruct()

#     log.info('END!')


@app.middleware("http")
async def log_requests(request: Request, call_next: Callable) -> Response:
    log.debug(f"Received request: {request.method} {request.url}")

    response = await call_next(request)

    log.debug(f"Sent response: {response.status_code} {response.headers}")

    return response


def get_session():
    with dbi.se() as session:
        yield session



def make_datafile_source_url(script:schema.Script, filename):
    global serializers

    found = False
    src = script.get_data_dir()

    for k, v in serializers.items():
        if v.test_source_matches(src):
            log.debug(f'serializer "{k}" matched for {src}')
            return v.make_source(src, filename)
            
    if not found:
        raise HTTPException(status_code=400, detail=f"Invalid data dir in script {script.id}!")


@app.get("/ui")
async def ui0(request: Request):
    template = templates.get_template(f'pg_home.html')
    context = {"url_for": request.url_for}
    rendered_html = template.render(context)
    return HTMLResponse(status_code=200, content=rendered_html)

@app.get("/ui/{page}")
async def ui(page:str, request: Request):
    template = templates.get_template(f'pg_{page}.html')
    context = {"url_for": request.url_for}
    rendered_html = template.render(context)
    return HTMLResponse(status_code=200, content=rendered_html)



@app.get("/info")
def info():
    return {'t_started': t_started, 'schema': schema.schema_dc, 'sys_info': helpers.get_sys_info()}



@app.get("/ping")
@app.get("/")
def ping():
    st = f'<h1>JupyRunner DB/API Server</h1>'
    st += f'<p>version: v{JupyRunner.__version__}</p>'
    st += f'<p>status: RUNNING, DB-connection: "{dbi.engine.url}"</p>'
    st += f'<p>running since: "{helpers.make_zulustr(t_started)}"</p>'
    st += f'<p>local time: "{helpers.iso_now()}"</p>'

    st += f"""<hr>
    <ul>
        <li><a href="/ui/home">Open Main UI</a></li>    
        <li><a href="/docs">Open API documentation (swagger like webpage)</a></li>    
        <li>default_dir_data:
            <ul>
                <li>path: <a href="/files/data">{filesys_storage_api.default_dir_data}</a></li>
                <li>exists: {os.path.exists(filesys_storage_api.default_dir_data)}</a></li>
            </ul>
        </li>
        <li>default_dir_repo:
            <ul>
                <li>path: <a href="/files/repo">{filesys_storage_api.default_dir_repo}</a></li>
                <li>exists: {os.path.exists(filesys_storage_api.default_dir_repo)}</li>
            </ul>
        </li>
        <li>{template_dir=}</li>
        <li>{static_dir=}</li>
    </ul>
    <hr>
    <pre>{helpers.get_sys_info()}</pre>
    """

    s = f"""
    <!DOCTYPE html>
        <html lang="en">
    <body>
        {st}
    </body>
    </html>
    """

    

    return HTMLResponse(content=s, status_code=200)


class ConstructScriptRequest(BaseModel):
    script_in_path: str = '/home/jovyan/shared/repos/example_script.ipynb'
    script_params_json: dict | None = {'param1': 1}
    start_condition: datetime.datetime | None = helpers.now_iso()
    end_condition: datetime.datetime | None = helpers.tomorrow_iso()
    device_id: str | None = None

@app.post("/construct/script")
def construct_route(request: ConstructScriptRequest):
    # try:
    result = schema.Script.construct(
        script_in_path=request.script_in_path,
        script_params_json=request.script_params_json,
        start_condition=request.start_condition,
        end_condition=request.end_condition,
        device_id=request.device_id
    )
    return {"result": result}
    # except Exception as e:
    #     raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    

class ConstructDataFileRequest(BaseModel):
    source: str = ''
    script_params_json: dict | None = {'param1': 1}
    start_condition: datetime.datetime | None = helpers.now_iso()
    end_condition: datetime.datetime | None = helpers.tomorrow_iso()
    device_id: str | None = None

# Get all scripts
@app.get("/example/script")
def script_example():
    return schema.Script.construct('/home/jovyan/shared/repos/example_script.ipynb', {'param1': 1}, device_id='rx_i5b_24')


# Get all scripts
@app.get("/example/device")
def device_example(device_id: str = Query(default_factory=lambda : f'dut_{int(time.time())}', description='the device id to assign')):
    return schema.Device(id=device_id)


# Get all scripts
@app.get("/script")
def get_scripts():
    return dbi.get_all(schema.Script)


# Get a specific script by ID
@app.get("/script/{script_id}")
def get_script(script_id: int):
    obj = dbi.get(schema.Script, script_id)
    log.debug(f'{obj.device=}')
    if not obj:
        raise HTTPException(status_code=404, detail="Script not found")
    return obj

# Create a new script
@app.post("/script")
def create_script(script: schema.Script) -> schema.Script:
    log.debug('POST /script')
    res = dbi.commit(script)
    log.debug(f'POST /script -> {res=}')
    return res


# Get all devices
@app.get("/device")
def get_devices() -> list[schema.Device]:
    return dbi.get_all(schema.Device)

# Get a specific device by ID
@app.get("/device/{device_id}")
def get_device(device_id: str) -> schema.Device:
    obj = dbi.get(schema.Device, device_id)
    if not obj:
        raise HTTPException(status_code=404, detail="device not found")
    log.debug(f'{obj.scripts=}')
    return obj


# Create a new device
@app.post("/device")
async def create_device(device: schema.Device) -> schema.Device:
    # dc = await request.json()
    log.debug(f'POST /device {device.model_dump()=}')
    res = dbi.commit(device)
    log.debug(f'POST /device -> {res=} {res.model_dump()=}')
    
    return res


# Get all data files
@app.get("/datafile")
def get_datafiles():
    return dbi.get_all(schema.Device)

# Get a specific data file by ID
@app.get("/datafile/{datafile_id}")
def get_datafile(datafile_id: int):  # Assuming ID is an integer for datafiles
    obj = dbi.get(schema.Datafile, datafile_id)
    if not obj:
        raise HTTPException(status_code=404, detail="datafile not found")
    return obj

# Create a new data file
@app.post("/datafile")
def create_datafile(datafile: schema.Datafile):
    return dbi.commit(datafile)

@app.patch("/script/{script_id}")
async def patch_script(script_id:int, request: Request):
    return dbi.set_property(schema.Script, script_id, **(await request.json()))
    
@app.put("/script/{script_id}")
def put_script(script_id:int, script: schema.Script):
    assert script_id == script.id, f'trying to set a object with mismatching id! {script_id=} vs. {script.id=}'
    return dbi.commit(script)

@app.patch("/device/{device_id}")
async def patch_device(device_id:str, request: Request):
    return dbi.set_property(schema.Device, device_id, **(await request.json()))
    
@app.put("/device/{device_id}")
def put_device(device_id:str, device: schema.Device):
    assert device_id == device.id, f'trying to set a object with mismatching id! {device_id=} vs. {device.id=}'
    return dbi.commit(device)

@app.patch("/datafile/{datafile_id}")
async def patch_datafile(datafile_id:int, request: Request):
    return dbi.set_property(schema.Datafile, datafile_id, **(await request.json()))
    
@app.put("/datafile/{datafile_id}")
def put_datafile(datafile_id:int, datafile: schema.Datafile):
    assert datafile_id == datafile.id, f'trying to set a object with mismatching id! {datafile_id=} vs. {datafile.id=}'
    return dbi.commit(datafile)

@app.put("/projectvariable/{var_id}")
def put_var(var_id:str, obj: schema.ProjectVariable):
    assert var_id == obj.id, f'trying to set a object with mismatching id! {var_id=} vs. {obj.id=}'
    return dbi.commit(obj)

@app.post("/projectvariable")
def post_var(obj: schema.ProjectVariable):
    return dbi.commit(obj)

@app.get("/projectvariable/{var_id}")
def get_var(var_id:str):
    obj = dbi.get(schema.ProjectVariable, var_id)
    if not obj:
        raise HTTPException(status_code=404, detail="datafile not found")
    return obj

@app.get("/projectvariable")
def get_var():
    return dbi.get_all()





@app.post("/action/script/{script_id}/upload_data_many_js")
async def action_script_upload_many_js(
    script_id: str, files: list[UploadFile] = File(...)
):
    try:
        print(f'/action/script/{script_id}/upload_data_many_js: received upload request for N={len(files)} files to script_id={script_id}')
        return _action_script_upload_many(script_id, files)    
    except Exception as err:
        log.error(err)

@app.post("/action/script/{script_id}/upload_data_many")
async def action_script_upload_many(script_id:int, files: list[UploadFile] = File(...)):
    try:
        return _action_script_upload_many(script_id, files)    
    except Exception as err:
        log.error(err)

@app.post("/action/script/{script_id}/upload_data")
async def action_script_upload_many(script_id, file: UploadFile = File(...)):
    return _action_script_upload_many(script_id, [file])


def _action_script_upload_many(script_id:int, files: list[UploadFile] = File(...)):
    log.info(f'received upload request for N={len(files)} files to script_id={script_id}')
    with dbi.se() as session:
        script = session.get(schema.Script, script_id)
        if script is None:
            raise HTTPException(status_code=404, detail=f"Script {script_id=} not found in db")

        ddir = script.get_data_dir().replace('\\', '/')
        datafile_objs = []
        for file in files:
            filename = file.filename if file.filename else f"default_datafile_{time.time()}.data"
            dtaf = schema.Datafile(script_id=script.id, device_id=script.device_id, source=f'{ddir}/{filename}')
            datafile_objs.append(dbi.add_to_db(session, dtaf))

    return _upload_and_register_files(datafile_objs, files)

@app.post("/action/datafile/upload")
async def action_urf_single(datafile_obj: schema.Datafile, file: UploadFile = File(...)):
    """same as upload_and_register_files but for a single file"""
    return _upload_and_register_files({file.filename:datafile_obj}, [file])


@app.post("/action/datafile/upload_many")
async def action_urf_many(datafile_objs: Dict[str, schema.Datafile], files: list[UploadFile] = File(...)):
    """
    Uploads and registers data files asynchronously.

    This function takes a dictionary of `DataFile` objects and a list of uploaded files.
    It performs the following steps:

    1. Asserts that each uploaded file's filename exists in the `datafile_objs` dictionary.
    2. Sets the MIME type of each `DataFile` object based on the corresponding uploaded file.
    3. Infers the data type of each `DataFile` object based on the MIME type:
        - If the MIME type contains "text", the data type is set to `schema.DATAFILE_TYPE.TEXTFILE`.
        - If the MIME type contains "pandas", the data type is set to `schema.DATAFILE_TYPE.DATAFRAME`.
        - Otherwise, the data type is set to `schema.DATAFILE_TYPE.BINARY`.
    4. Iterates through registered serializers and tries to find a compatible one for each data file.
        - If a matching serializer is found, it is used to upload the data file content.
        - If no matching serializer is found, an HTTPException with status code 400 is raised.
    5. Uses the `dbi` to add all data files to the database.
    6. Returns a dictionary containing a success message, a success flag, and the result
       from the database operation.

    Raises:
        HTTPException (status_code=500): If an error occurs during file upload or database operation.

    Args:
        datafile_objs: A dictionary mapping filenames (str) to `schema.DataFile` objects.
        files: A list of uploaded files using the `UploadFile` type.

    Returns:
        A dictionary containing a success message, success flag, and the database operation result.
    """
    return _upload_and_register_files(datafile_objs, files)

@app.post("/action/datafile/upload")
async def action_urf_single(datafile_obj: schema.Datafile, file: UploadFile = File(...)):
    """same as upload_and_register_files but for a single file"""
    return _upload_and_register_files({file.filename:datafile_obj}, [file])


class UploadFilesToScriptRequest(BaseModel):
    script_in_path: str = '/home/jovyan/shared/repos/example_script.ipynb'
    script_params_json: dict | None = {'param1': 1}
    start_condition: datetime.datetime | None = helpers.now_iso()
    end_condition: datetime.datetime | None = helpers.tomorrow_iso()
    device_id: str | None = None

@app.post("/action/script/{script_id}/upload/files")
async def upload_files_for_script(script_id: int, request: Request, files: list[UploadFile] = File(...)) -> Dict[str, Any]:
    """
    Uploads files associated with a script asynchronously.

    This function handles uploading files for a specific script identified by the `script_id`.
    It retrieves the script object from the database and performs the following:

    1. Retrieves any additional JSON data from the request body.
    2. Validates that the request body doesn't explicitly set reserved fields:
        - `script_id`: This field should be provided through the path parameter.
        - `device_id`: This field should be retrieved from the associated script.
        - `file_type`: This field is determined based on the file extension.
        - `source`: This field is generated from the script information and filename.
    3. Creates a dictionary to store `DataFile` objects with filenames as keys.
    4. Iterates through each uploaded file:
        - Extracts the filename and extension.
        - Determines the data type based on the extension (e.g., `.df`, `.dataframe`, `.pandas` for DataFrame).
        - Generates a unique filename for DataFrames to ensure consistency (appends '.csv' extension).
        - Constructs a `DataFile` object based on script information, filename, data type, and source URL.
    5. Calls the `_upload_and_register_files` function to handle data upload and registration.

    Raises:
        HTTPException (status_code=404): If the script with the provided `script_id` is not found.

    Args:
        script_id: The ID of the script to associate the uploaded files with.
        request: The FastAPI request object for accessing additional data.
        files: A list of uploaded files using the `UploadFile` type.

    Returns:
        The dictionary returned by the `_upload_and_register_files` function,
        containing information about the upload result and success status.
    """

    kwargs = await request.json()

    script = dbi.get(schema.Script, script_id)
    if not script:
        raise HTTPException(status_code=404, detail="datafile not found")
    
    
    for k in "script_id device_id file_type source".split():
        assert not k in kwargs, 'can not explicitly set "{k}" with this route! please use the /action/upload/datafile(s) route(s) directly for this!'

    datafile_objs = {}
    for file in files:
        name, extension = os.path.splitext(file.filename)

        if extension in ['df', 'dataframe', 'pandas']:
            file_type = schema.DATAFILE_TYPE.DATAFRAME
            filename = name + '.csv'
        else:
            file_type = schema.DATAFILE_TYPE.UNKNOWN
            filename = file.filename

        source = make_datafile_source_url(script, filename)

        datafile_objs[file.filename] = schema.Datafile(
                        script_id=script_id, 
                        device_id=script.device_id, 
                        file_type=file_type, 
                        source=source)

    return _upload_and_register_files(datafile_objs, files)



async def _upload_and_register_files(datafile_objs: Dict[str, schema.Datafile], files: list[UploadFile] = File(...)):
    global serializers

    try:
        for file in files:
            assert file.filename in datafile_objs, f'the uploaded file {file.filename=} is not in the corresponding dict of datafile objects! make sure you give a valid datafile_obj for each dict uploaded file!'

            datafile = datafile_objs[file.filename]
            datafile.mime_type = file.content_type
            if datafile.data_type == schema.DATAFILE_TYPE.UNKNOWN:
                if 'text' in datafile.mime_type:
                    datafile.data_type = schema.DATAFILE_TYPE.TEXTFILE
                elif 'pandas' in datafile.mime_type:
                    datafile.data_type = schema.DATAFILE_TYPE.DATAFRAME
                else:
                    datafile.data_type = schema.DATAFILE_TYPE.BINARY

            found = False
            for k, v in serializers.items():
                if v.test_source_matches(datafile):
                    log.info(f'serializer "{k}" matched for {datafile}')
                    v.upload(datafile, file)

            if not found:
                raise HTTPException(status_code=400, detail="Invalid source in datafile!")

        res = dbi.add_many(list(datafile_objs.values()))
        return {"message": "Data file uploaded successfully", "success": True, "result": res}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error uploading data file: {str(e)}")
    
@app.get("/qry/tabledata")
async def qry_scripts(start_date:datetime.datetime|None=Query(default=None), 
                end_date:datetime.datetime|None=Query(default=None), 
                stati:list[schema.STATUS]|None=Query(default=None),
                script_name:str=Query(default=''),
                script_in_path:str=Query(default=''),
                script_version:str=Query(default=''),
                out_path:str=Query(default=''),
                n_max:int=Query(default=-1), skipn:int=Query(default=0)):
    dc = dbi.qry_tabledata(t_min=start_date, t_max=end_date, stati=stati, script_name=script_name, script_in_path=script_in_path, script_version=script_version, 
                             out_path=out_path, n_max=n_max, skipn=skipn)
    return dc

@app.get("/qry/script")
async def qry_scripts(t_min:datetime.datetime|None=Query(default=None), 
                t_max:datetime.datetime|None=Query(default=None), 
                stati:list[schema.STATUS]|None=Query(default=None),
                script_name:str=Query(default=''),
                script_in_path:str=Query(default=''),
                script_version:str=Query(default=''),
                out_path:str=Query(default=''),
                n_max:int=Query(default=-1), skipn:int=Query(default=0)):
    return dbi.qry_scripts(t_min=t_min, t_max=t_max, stati=stati, script_name=script_name, script_in_path=script_in_path, script_version=script_version, 
                             out_path=out_path, n_max=n_max, skipn=skipn)

@app.get("/qry/script/{script_id}/datafiles")
async def ids_projectvariable(script_id:int):
    with dbi.se() as session:
        script = session.get(schema.Script, script_id)
        if not script:
            raise HTTPException(status_code=404, detail="script not found")
        return script.datafiles

@app.get("/qry/script/{script_id}/params")
async def ids_projectvariable(script_id:int):
    with dbi.se() as session:
        script = session.get(schema.Script, script_id)
        if not script:
            raise HTTPException(status_code=404, detail="script not found")
        return script.script_params_json


@app.get("/qry/device/{device_id}/datafiles")
async def ids_projectvariable(device_id:str):
    with dbi.se() as session:
        d = session.get(schema.Device, device_id)
        if not d:
            raise HTTPException(status_code=404, detail="device not found")
        return d.datafiles

@app.get("/qry/device/{device_id}/scripts")
async def ids_projectvariable(device_id:str):
    with dbi.se() as session:
        d = session.get(schema.Device, device_id)
        if not d:
            raise HTTPException(status_code=404, detail="device not found")
        return d.scripts


@app.get(f"/qry/ids/projectvariable")
async def ids_projectvariable(request: Request):
    return dbi.get_ids(schema.ProjectVariable, n_max=-1)

@app.get(f"/qry/ids/script")
async def ids_script(request: Request):
    return dbi.get_ids(schema.Script, n_max=-1)

@app.get(f"/qry/ids/device")
async def ids_device(request: Request):
    return dbi.get_ids(schema.Device, n_max=-1)

@app.get(f"/qry/ids/datafile")
async def ids_datafile(request: Request):
    return dbi.get_ids(schema.Datafile, n_max=-1)




@app.get("/qry/get_last_n/script")
def qry_get_last_n_scripts(n:int=Query(default=10),
                as_id:int=Query(default=0, description='0|1 whether or not to only return the id'))-> list[schema.Script|None]:
    return [s.id if as_id else s for s in dbi.qry_scripts(n_max=n) if s]


@app.get("/last")
@app.get("/qry/get_last/script")
def qry_get_last_script() -> schema.Script|None:
    return next(iter(dbi.qry_scripts(n_max=1)), None)




@app.get("/action/kill/{script_int}")
def kill(script_id:int):
    
    with dbi.se() as session:

        script = session.get(script_id)
        if script is None:
            raise HTTPException(status_code=404, detail=f"Script {script_id=} not found in db")
        status = script.status
        nr = schema.status_dc[status]
        if nr < 10:
            script.status = schema.STATUS.ABORTED
            res = dict(success=True, info=f"ID <{script_id=}> status: {status} --> ABORTED", status=script.status)
        elif nr > 100:
            res = dict(success=True, info=f"ID <{script_id=}> status: {status} | can't kill because job has stopped", status=script.status)
        else:
            script.status = schema.STATUS.CANCELLING
            res = dict(success=True, info=f"ID <{script_id=}> status: {status} --> CANCELLING", status=script.status)
        dbi.add_to_db(session, script)
        
    return res


@app.get("/action/cancle/{script_int}")
@app.get("/action/cancel/{script_int}")
def cancel(script_id:int):
    
    with dbi.se() as session:

        script = session.get(script_id)
        if script is None:
            raise HTTPException(status_code=404, detail=f"Script {script_id=} not found in db")
        status = script.status
        nr = schema.status_dc[status]
        if nr < 10:
            info = f"ERROR: ID <{script_id=}> status: {status} | can't cancel because not started yet use abort instead"
            res = dict(success=False, info=info, status=script.status)
        elif nr > 100:
            info = f"ERROR: ID <{script_id=}> status: {status} | can't cancel because job has stopped"
            res = dict(success=False, info=info, status=script.status)
        else:
            script.status = schema.STATUS.CANCELLING
            
            info = f"ID <{script_id=}> status: {status} --> CANCELLING"
            res = dict(success=True, info=info, status=script.status)
        dbi.add_to_db(session, script)
        
    return res



@app.get("/action/abort/{script_int}")
def abort(script_id:int):
    
    with dbi.se() as session:

        script = session.get(script_id)
        if script is None:
            raise HTTPException(status_code=404, detail=f"Script {script_id=} not found in db")
        status = script.status
        nr = schema.status_dc[status]
        if nr < 10:
            script.status = schema.STATUS.ABORTED
            info = f"ID <{script_id=}> status: {status} --> ABORTED"
            res = dict(success=True, info=info, status=script.status)
        else:
            info = f"ERROR: ID <{script_id=}> status: {status} | can't abort anymore use cancel instead"
            res = dict(success=False, info=info, status=script.status)

        dbi.add_to_db(session, script)
        
    return res



@app.get("/action/script/run")
async def action_script_run(request: Request):
    """
    Runs a script based on the provided parameters.

    This endpoint accepts query parameters and constructs a `Script` object.
    It validates the `script_in_path` parameter and attempts to resolve it
    from the repository if it doesn't exist locally.
    If a `device_id` is provided, it ensures the device exists in the database.
    Finally, it adds the script to the database.

    Args:
        request: The incoming FastAPI request object.

    Returns:
        A dictionary containing the success status, kwargs, and the database result.
    """

    kwargs = helpers.split_flat_dict_into_nested(await request.query_params)
    return _action_script(kwargs, False)



@app.get("/action/script/pre_test")
async def action_script_pre_test(request: Request):
    kwargs = helpers.split_flat_dict_into_nested(await request.query_params)
    return _action_script(kwargs, True)


@app.post("/action/script/pre_test")
async def action_script_pre_test(request: Request):
    kwargs = helpers.split_flat_dict_into_nested(await request.json())
    return _action_script(kwargs, True)

@app.post("/action/script/run")
async def action_script_run(request: Request):
    kwargs = helpers.split_flat_dict_into_nested(await request.json())
    return _action_script(kwargs, False)

def _action_script(kwargs, test_only=False):
    errormsg = ''
    res = {}
    success = True
    try:
        assert 'script_in_path' in kwargs, 'need to give at least script_in_path! in query params'

        script_in_path = kwargs.get('script_in_path')
        assert script_in_path, f'"script_in_path" can not be empty!'
        if not os.path.exists(script_in_path):
            repo_scripts = filesys_storage_api.get_scripts_in_repo()
            for scriptname in repo_scripts:
                if script_in_path in os.path.basename(scriptname):
                    kwargs['script_in_path'] = scriptname
                    break
            
        device_id = kwargs.get('device_id')
        if device_id:
            assert dbi.get(schema.Device, device_id), f'the given {device_id=} does not exist in the database!'

        assert os.path.exists(kwargs['script_in_path']), f'given path {script_in_path=} does not exist'
        res = scriptrunner.pre_check(schema.Script(**kwargs))

        if not test_only:    
            res = dbi.commit(schema.Script(**kwargs))
    except Exception as err:
        success = False
        errormsg = f'ERROR: {type(err)=} | {err=}'
    color = 'danger' if errormsg else ('info' if test_only else 'success')
    info = 'success' if success else errormsg
    return {'success': success, 'kwargs': kwargs, 'info': info, 'result': res, 'test_only': test_only, 'error': errormsg, 'color': color}





@app.get('/action/script/rerun/{script_id}')  
def action_script_rerun(script_id:int):
    try:

        with dbi.se() as session:
            
            obj = session.get(script_id)
            if obj is None:
                raise HTTPException(status_code=404, detail=f"Script {script_id=} not found in db")
        
            obj_old = obj.model_dump()

            status = obj.status
            err = helpers.limit_len('' if not obj.errors else obj.errors)
            obj.comments = str(obj.comments) + f'<<< [{helpers.now_iso()}] | rerun of original run with status="{status.name}" and {obj.time_started=} ... {obj.time_finished=} with err="{err}" requested now >>>'

            obj.status = schema.STATUS.AWAITING_CHECK
            obj.errors = ''
            obj.time_started = ''

        return dict(command='rerun', id=script_id, success=True, status=obj.status, comments=obj.comments, obj_new = obj, obj_old=obj_old)
    
    except Exception as err:
        log.exception(err)
        s = traceback.format_exception(err, limit=5)
        return dict(error=s), 500


@app.get("/repo/get/filenames")
async def repo_get_filenames() -> list[str]:
    return filesys_storage_api.get_scripts_in_repo()

@app.get("/repo/get/dirname")
async def repo_get_dirname() -> str:
    return filesys_storage_api.default_dir_repo.replace('\\', '/')

@app.get("/repo/get/params")
async def repo_get_params(script_name : str = Query(default='', description='The script path to get the params for')) -> dict[str,dict] | dict:
    repo = filesys_storage_api.default_dir_repo
    scripts = helpers_papermill.get_repo_scripts(repo)
    
    fun = helpers_papermill.get_params
    if not script_name:
        return {k:fun(scripts[k]) for k in scripts}
    
    if script_name and script_name in scripts:
        return fun(scripts[script_name])

    dc = {k.replace('\\', '/'):fun(v) for k, v in scripts.items() if script_name in k}
    if dc: 
        return dc
    
    raise HTTPException(status_code=404, detail=f"Script {script_name=} not found in repo {repo}")

@app.get("/repo/get/all")
async def repo_get_params(script_name : str = Query(default='', description='The script path to get the params for')) -> dict[str,dict] | dict:
    repo = filesys_storage_api.default_dir_repo
    scripts = helpers_papermill.get_repo_scripts(repo)

    if scripts: 
        return scripts
    
    if not script_name:
        return []
    
    raise HTTPException(status_code=404, detail=f"Script {script_name=} not found in repo {repo}")







@app.get("/show/{path:path}")
async def send_report(path: str, request: Request):
    log.debug(f'"/show" with{path=}' )
    if path.startswith("home/"):
        path = "/" + path



    if path and path.endswith('.ipynb'):
        n = len('.ipynb')
        npath = path[:-n] + '.html'
    else:
        npath = ''

    if os.path.exists(path):
        if path and path.endswith('.ipynb'):
            if not filesys_storage_api.default_dir_data in path:
                html_exporter = nbconvert.HTMLExporter()
                html_data, resources = html_exporter.from_filename(path)
                return HTMLResponse(html_data, status_code=200)
            else:
                n = len('.ipynb')
                npath = path[:-n] + '.html'
                if not os.path.exists(path) and os.path.exists(npath):
                    path = npath
                if not os.path.exists(npath):
                    html_exporter = nbconvert.HTMLExporter()
                    html_data, resources = html_exporter.from_filename(path)
                    with open(npath, "w", encoding='utf-8') as f:
                        f.write(html_data)
                
                path = npath

    elif not os.path.exists(path) and os.path.exists(npath):
        path = npath
    else:
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path)

@app.get("/files/data/{path:path}")
async def serve_files(path: str = ''):
    return await _serve_files('data', filesys_storage_api.default_dir_data, path)

@app.get("/files/repo/{path:path}")
async def serve_files(path: str = ''):
    return await _serve_files('repo', filesys_storage_api.default_dir_repo, path)

async def _serve_files(k, base_dir, path):
    file_path = os.path.join(base_dir, path)
    if os.path.isdir(file_path):
        return await list_directory(k, file_path)
    elif os.path.isfile(file_path):
        return FileResponse(file_path)
    else:
        raise HTTPException(status_code=404, detail="File or directory not found")

async def list_directory(k, directory_path):
    files = os.listdir(directory_path)
    html_content = f"<h2>Directory: {directory_path}</h2>Files:<ul>"

    for file_name in files:
        file_path = os.path.join(directory_path, file_name)
        if os.path.isdir(file_path):
            html_content += f"<li>DIR:  <a href='/files/{k}/{file_path}'>{file_name}</a></li>"
        else:
            html_content += f"<li>FILE: <a href='/show/{file_path}'>{file_name}</a></li>"
    html_content += "</ul>"
    return Response(html_content, media_type="text/html")

# # Delete a script
# @app.delete("/scripts/{script_id}")
# def delete_script(script_id: int):
#     with Session(engine) as session:
#         script = session.get(Script, script_id)
#         if not script:
#             raise HTTPException(status_code=404, detail="Script not found")
#         session.delete(script)
#         session.commit()
#         return {"message": "Script deleted successfully"}

# # Delete a result
# @app.delete("/results/{result_id}")
# def delete_result(result_id: int):
#     with Session(engine) as session:
#         result = session.get(Result, result_id)
#         if not result:
#             raise HTTPException(status_code=404, detail="Result not found")
#         session.delete(result)
#         session.commit()
#         return {"message": "Result deleted successfully"}

# # Delete a device
# @app.delete("/devices/{device_id}")
# def delete_device(device_id: str):
#     with Session(engine) as session:
#         device = session.get(Device, device_id)
#         if not device:
#             raise HTTPException(status_code=404, detail="Device not found")
#         session.delete(device)
#         session.commit()
#         return {"message": "Device deleted successfully"}

# # Delete a project variable
# @app.delete("/project_variables/{variable_id}")
# def delete_project_variable(variable_id: str):
#     with Session(engine) as session:
#         variable = session.get(ProjectVariable, variable_id)
#         if not variable:
#             raise HTTPException(status_code=404, detail="Project variable not found")
#         session.delete(variable)
#         session.commit()
#         return {"message": "Project variable deleted successfully"}
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)