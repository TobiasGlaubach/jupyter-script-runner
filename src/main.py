
from contextlib import asynccontextmanager
import datetime
import os
import time
import traceback
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from pydantic import BaseModel, Field
from JupyRunner.core import db_interface as dbi
from JupyRunner.core import schema, helpers, filesys_storage_api, helpers_mattermost, helpers_papermill
from JupyRunner.io import nextcloud_api, redmine_api, local_filesys_api

import yaml

log = helpers.log


with open('config.yaml', 'r') as fp:
    config = yaml.safe_load(fp)


modules = [dbi, filesys_storage_api]
serializers = {
    'nextcloud': nextcloud_api,
    'redmine': redmine_api,
    'filesys': local_filesys_api,
}

for module in modules:
    module.setup(config)

for module in modules:
    print(module)
    module.start(config)

serializers = {k:v.start(config) for k, v in serializers.items()}

log.info('STARTED!')

app = FastAPI()

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global serializers

#     log.info('STARTED!')

#     yield

#     for k, v in serializers.items():
#         v.destruct()

#     log.info('END!')





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



@app.get("/info")
def info():
    return schema.schema_dc



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
    if not obj:
        raise HTTPException(status_code=404, detail="Script not found")
    return obj

# Create a new script
@app.post("/script")
def create_script(script: schema.Script):
    return dbi.commit(script)


# Get all devices
@app.get("/device")
def get_devices():
    return dbi.get_all(schema.Device)

# Get a specific device by ID
@app.get("/device/{device_id}")
def get_device(device_id: str):
    obj = dbi.get(schema.Device, device_id)
    if not obj:
        raise HTTPException(status_code=404, detail="device not found")
    return obj

# Create a new device
@app.post("/device")
def create_device(device: schema.Device):
    return dbi.commit(device)
    



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


for k, v in {'script': schema.Script, 'datafile': schema.Datafile, 'device': schema.Device}.items():
    @app.patch(f"/{k}/" + "{object_id}")
    def patch_obj(object_id, request: Request):
        return dbi.set_property(v, object_id, request.json())
        
    @app.put(f"/{k}/" + "{object_id}")
    def put_obj(object_id, obj: v):
        assert object_id == obj.id, f'trying to set a object with mismatching id! {object_id=} vs. {obj.id=}'
        return dbi.commit(obj)




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
async def qry_scripts(t_min:datetime.datetime|None=Query(default=None), 
                t_max:datetime.datetime|None=Query(default=None), 
                stati:list[schema.STATUS]|None=Query(default=None),
                script_name:str=Query(default=''),
                script_version:str=Query(default=''),
                out_path:str=Query(default=''),
                n_max:int=Query(default=-1), skipn:int=Query(default=0)):
    dc = dbi.qry_tabledata(t_min=t_min, t_max=t_max, stati=stati, script_name=script_name, script_version=script_version, 
                             out_path=out_path, n_max=n_max, skipn=skipn)
    return dc

@app.get("/qry/script")
async def qry_scripts(t_min:datetime.datetime|None=Query(default=None), 
                t_max:datetime.datetime|None=Query(default=None), 
                stati:list[schema.STATUS]|None=Query(default=None),
                script_name:str=Query(default=''),
                script_version:str=Query(default=''),
                out_path:str=Query(default=''),
                n_max:int=Query(default=-1), skipn:int=Query(default=0)):
    return dbi.qry_scripts(t_min=t_min, t_max=t_max, stati=stati, script_name=script_name, script_version=script_version, 
                             out_path=out_path, n_max=n_max, skipn=skipn)

for k, v in schema.schema_cls_dc_inv.items():
    @app.get(f"/qry/ids/{k}")
    async def ids_k(request: Request):
        return dbi.get_ids(v, n_max=-1)
    

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

    assert 'script_in_path' in kwargs, 'need to give at least script_in_path! in query params'

    script_in_path = kwargs.get('script_in_path')
    assert script_in_path, f'"script_in_path" can not be empty!'
    if not os.path.exists(script_in_path):
        repo_scripts = filesys_storage_api.get_scripts_in_repo()
        for scriptname in repo_scripts:
            if script_in_path in os.path.basename(scriptname):
                kwargs['script_in_path'] = scriptname
                break
    device_id = kwargs.get('script_in_path')
    if device_id:
        assert dbi.get(device_id), f'the given {device_id=} does not exist in the database!'

    assert os.path.exists(kwargs['script_in_path']), f'given path {script_in_path=} does not exist'
    res = dbi.commit(schema.Script(**kwargs))
    return {'success': True, 'kwargs': kwargs, 'result': res}




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
            obj.comments = str(obj.comments) + f'<<< [{helpers.now_iso()}] | rerun of original run with status="{status.name}" and {obj.time_started_iso=} ... {obj.time_finished_iso=} with err="{err}" requested now >>>'

            obj.status = schema.STATUS.AWAITING_CHECK
            obj.errors = ''
            obj.time_started_iso = ''

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
    return filesys_storage_api.default_dir_repo

@app.get("/repo/get/params")
async def repo_get_params(script_name : str = Query(default='', description='The script path to get the params for')) -> dict[str,dict] | dict:
    repo = filesys_storage_api.default_dir_repo
    scripts = helpers_papermill.get_repo_scripts(repo)
    
    fun = helpers_papermill.get_params
    if not script_name:
        return {k:fun(scripts[k]) for k in scripts}
    
    if script_name and script_name in scripts:
        return {script_name:fun(scripts[script_name])}

    dc = {k:fun(v) for k, v in scripts.items() if script_name in k}
    if dc: 
        return dc
    
    raise HTTPException(status_code=404, detail=f"Script {script_name=} not found in repo {repo}")



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