
from contextlib import asynccontextmanager
import datetime
import json
import os
import subprocess
import time
import traceback
from typing import Annotated, Any, Callable, Dict, List
import zipfile
import nbconvert
import pydocmaker as pyd
import urllib.parse
import asyncio

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

modules = [dbi, filesys_storage_api, scriptrunner]
serializers = {
    'nextcloud': nextcloud_api,
    'redmine': redmine_api,
    'local': local_filesys_api,
}

serializers_doc = {k:v for k, v in serializers.items()}

for module in modules:
    module.setup(config)

for module in modules:
    module.start(config)


redmine_api.setup(config['wiki_uploader'])


serializers = {k:v.start(config) for k, v in serializers.items() if k in config.get('storage_locations')}

log.info('STARTED!')

app = FastAPI()
templates = Jinja2Templates(directory="templates")  # You can use this for more complex templates
app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Environment(loader=FileSystemLoader("templates"))
app.mount("/data", StaticFiles(directory=filesys_storage_api.default_dir_data), name="data")  # Assuming a static directory
app.mount("/repos", StaticFiles(directory=filesys_storage_api.default_dir_repo), name="repos")  # Assuming a static directory
app.mount("/loose_docs", StaticFiles(directory=filesys_storage_api.default_dir_docs), name="loose_docs")  # Assuming a static directory
app.mount("/libs", StaticFiles(directory=filesys_storage_api.default_dir_libs), name="libs")  # Assuming a static directory


feedback_requests = {}
feedback_answers = {}

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

        if v.test_should_upload(src):
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
        <li>db:
            <ul>
                <li>path: {dbi.sqlite_file_name}</li>
                <li>exists: {os.path.exists(dbi.sqlite_file_name)}</li>
                <li>can_write: {helpers.can_write(dbi.sqlite_file_name)}</li>
                <li>can_write (dir): {helpers.can_write(os.path.dirname(dbi.sqlite_file_name))}</li>
            </ul>
        </li>
        <li>default_dir_data:
            <ul>
                <li>path: <a href="/files/data">{filesys_storage_api.default_dir_data}</a></li>
                <li>exists: {os.path.exists(filesys_storage_api.default_dir_data)}</li>
                <li>can_write: {helpers.can_write(filesys_storage_api.default_dir_data)}</li>
            </ul>
        </li>
        <li>default_dir_repo:
            <ul>
                <li>path: <a href="/files/repo">{filesys_storage_api.default_dir_repo}</a></li>
                <li>exists: {os.path.exists(filesys_storage_api.default_dir_repo)}</li>
                <li>can_write: {helpers.can_write(filesys_storage_api.default_dir_repo)}</li>
            </ul>
        </li>
        <li>default_dir_docs:
            <ul>
                <li>path: <a href="/files/loose_docs">{filesys_storage_api.default_dir_docs}</a></li>
                <li>exists: {os.path.exists(filesys_storage_api.default_dir_docs)}</li>
                <li>can_write: {helpers.can_write(filesys_storage_api.default_dir_docs)}</li>
            </ul>
        </li>
        <li>default_dir_libs:
            <ul>
                <li>path: <a href="/files/libs">{filesys_storage_api.default_dir_libs}</a></li>
                <li>exists: {os.path.exists(filesys_storage_api.default_dir_libs)}</li>
                <li>can_write: {helpers.can_write(filesys_storage_api.default_dir_libs)}</li>
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
def device_example(device_id: str = Query(default_factory=lambda : f'', description='the device id to assign')):
    return schema.Device(**{
      "id": "my_test_device" if not device_id else device_id,
      "source": "http://my_itop_server.domain",
      "address": "134.104.22.XX",
      "connection_protocol": "katcp",
      "configuration": "001-002-003-v1",
      "comments": "some example device which is linked to a device with the same name in iTop",
      "data_json": {'setup_config': {'args':[], 'kwargs': {}}} # data_json allows for any dicts to be stored in the database
    })


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

# Get a specific script by ID
@app.get("/script_full/{script_id}")
def rget_script_full(script_id: int):
    return get_script_full(script_id)

def get_script_full(script_id):
    with dbi.se() as session:
        obj = session.get(schema.Script, script_id)
        if not obj:
            raise HTTPException(status_code=404, detail="Script not found")
        dc = obj.model_dump()
        dc['device'] = obj.device.model_dump() if obj.device else {}
        dc['datafiles'] = [d.model_dump() for d in obj.datafiles]
    return dc

    
# Create a new script
@app.post("/script")
def create_script(script: schema.Script) -> schema.Script:
    log.debug('POST /script')
    assert script.id is None or script.id < 1725603466, f'{script.id=} are you trying to commit a timestamp to an id?'
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
    assert datafile.id is None or datafile.id < 1725603466, f'{datafile.id=} are you trying to commit a timestamp to an id?'
    return dbi.commit(datafile)

@app.patch("/script/{script_id}")
async def patch_script(script_id:int, request: Request):
    assert script_id is None or script_id < 1725603466, f'{script_id=} are you trying to commit a timestamp to an id?'
    return dbi.set_property(schema.Script, script_id, **(await request.json()))
    
@app.put("/script/{script_id}")
def put_script(script_id:int, script: schema.Script):
    assert script_id == script.id, f'trying to set a object with mismatching id! {script_id=} vs. {script.id=}'
    assert script_id is None or script_id < 1725603466, f'{script_id=} are you trying to commit a timestamp to an id?'
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
    assert datafile_id is None or datafile_id < 1725603466, f'{datafile_id=} are you trying to commit a timestamp to an id?'
    return dbi.set_property(schema.Datafile, datafile_id, **(await request.json()))
    
@app.put("/datafile/{datafile_id}")
def put_datafile(datafile_id:int, datafile: schema.Datafile):
    assert datafile_id == datafile.id, f'trying to set a object with mismatching id! {datafile_id=} vs. {datafile.id=}'
    assert datafile_id is None or datafile_id < 1725603466, f'{datafile_id=} are you trying to commit a timestamp to an id?'
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
    return dbi.get_all(schema.ProjectVariable)



@app.get("/downloadq")
async def download_file_qry(path: str = Query(...)):
    try:
        res = _download(path)
        if res == 404:
            raise HTTPException(status_code=404, detail="File or directory not found")
        
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")


@app.get("/download/{path:path}", response_model=None)
async def download_file(path: str) -> FileResponse|None:
    return _download(path)

def _download(path:str):
    log.info(f'download for path: {path}')
    
    p = path.lstrip('/')
    dd = filesys_storage_api.default_dir_data.rstrip('/')
    if not p.startswith(dd):
        file_path = dd + '/' + p
    else:
        file_path =  p
    assert file_path.startswith(dd), f'can only download from folder "{dd}" but you requested {file_path=}'

    if os.path.isfile(file_path):
        return FileResponse(file_path)
    elif os.path.isdir(file_path):
        zip_path = file_path + ".zip"
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for root, dirs, files in os.walk(file_path):
                for file in files:
                    zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), file_path))

        return FileResponse(zip_path)
    else:
        return 404


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
    return await _action_script_upload_many(script_id, [file])


async def _action_script_upload_many(script_id:int, files: list[UploadFile] = File(...)):
    log.info(f'received upload request for N={len(files)} files to script_id={script_id}')
    with dbi.se() as session:
        script = session.get(schema.Script, script_id)
        if script is None:
            raise HTTPException(status_code=404, detail=f"Script {script_id=} not found in db")

        ddir = script.get_data_dir().replace('\\', '/')
        datafile_objs = []
        for file in files:
            filename = file.filename if file.filename else f"default_datafile_{time.time()}.data"
            dtaf = schema.Datafile(script_id=script.id, device_id=script.device_id, file_path=f'{ddir}/{filename}')
            obj = dbi.add_to_db(session, dtaf)
            datafile_objs.append(obj)

    kwargs = await _upload_and_register_files(datafile_objs, files)

    with dbi.se() as session:
        for dfi_id, kw in kwargs.items():
            dbi.set_propert_sub(session, schema.Datafile, dfi_id, **kw)


    return {'success': True, 'script_id': script_id, 'filenames': [f for f in files]}


@app.post("/action/datafile/upload_many")
async def action_urf_many(datafile_objs: Dict[str, schema.Datafile], files: list[UploadFile] = File(...)):
    return await _upload_and_register_files(datafile_objs, files)


@app.post("/action/upload_data_many_js")
async def upload_files_for_script(script_id: int, files: Annotated[
        list[UploadFile], File(description="Multiple files to upload")
        ]):
    try:
        
        datafile_objs = filedict2datafiles(script_id, files)

        datafiles = dbi.add_many(list(datafile_objs.values()))
        datafile_objs = dict(zip(datafile_objs.keys(), datafiles))

        kwargs = await _upload_and_register_files(datafile_objs, files, ret_kwargs=True)

        ret = []
        nok = 0
        for datafile_id, kwrgs in kwargs.items():
            dfa_new = dbi.set_property(schema.Datafile, datafile_id, **kwrgs)
            assert not dfa_new.errors, f'DataFile with ID: {dfa_new.id} has errors:\n{dfa_new.errors}'
            assert dfa_new.status in [schema.STATUS_DATAFILE.READY, schema.STATUS_DATAFILE.EMPTY], f'status is not OK! {dfa_new.status=}, {dfa_new.errors=}'
            assert dfa_new.locations_storage_json, 'seems like nothing was uploaded!'
            ret.append(dfa_new.model_dump() if hasattr(dfa_new, 'model_dump') else str(dfa_new))
            if not dfa_new.status in [schema.STATUS_DATAFILE.ERROR, schema.STATUS_DATAFILE.FAULTY]:
                nok += 1
        

        pre = 'ERROR: only ' if nok != len(files) else 'SUCCESS: '
        context = {
            "res_info": f"{pre}N={nok}/{len(files)} Data file(s) uploaded sucessfully.",
            "res_color": 'danger' if nok != len(files) else 'success',
            "res_content": json.dumps({k.filename: v for k, v in zip(files, ret)}, indent=2, default=schema.json_serial),
            "res_content_color": "black"
        }

    
    except Exception as err:
        log.exception(err)
        context = {
            "res_info": f"ERROR: {err}",
            "res_color": 'danger',
            "res_content": traceback.format_exception(err, limit=5),
            "res_content_color": "red"
        }
    return context

    # template = templates.get_template(f'pg_upload_success.html')
    # rendered_html = template.render(context)
    # return HTMLResponse(status_code=200, content=rendered_html)


@app.post("/action/script/{script_id}/upload/files")
async def upload_files_for_script(script_id: int, files: Annotated[
        list[UploadFile], File(description="Multiple files to upload")
        ]) -> Dict[str, Any]:
    try:
        
        datafile_objs = filedict2datafiles(script_id, files)
        datafiles = dbi.add_many(list(datafile_objs.values()))
        datafile_objs = dict(zip(datafile_objs.keys(), datafiles))

        kwargs = await _upload_and_register_files(datafile_objs, files, ret_kwargs=True)

        ret = []
        for datafile_id, kwrgs in kwargs.items():
            dfa_new = dbi.set_property(schema.Datafile, datafile_id, **kwrgs)
            assert dfa_new.status in [schema.STATUS_DATAFILE.READY, schema.STATUS_DATAFILE.EMPTY], f'status is not OK! {dfa_new.status=}'
            assert dfa_new.locations_storage_json, 'seems like nothing was uploaded!'
            ret.append(dfa_new)

        return {"message": "Data file uploaded successfully", "success": True, "result": ret}
    except FileExistsError as err:
        return {"message": str(err), "success": False, "result": None}
    except Exception as err:
        log.exception(err)
        raise



def filedict2datafiles(script_id: int, files: list[UploadFile]):
    script = dbi.get(schema.Script, script_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"script with {script_id=} not found")

    datafile_objs = {}
    for file in files:


        name, extension = os.path.splitext(file.filename)

        if extension in ['df', 'dataframe', 'pandas']:
            file_type = schema.DATAFILE_TYPE.DATAFRAME
            filename = name + '.csv'
        elif extension in ['rep']:
            file_type = schema.DATAFILE_TYPE.REPORT
            filename = name + '.rep'
        else:
            file_type = schema.DATAFILE_TYPE.UNKNOWN
            filename = file.filename


        file_path = os.path.join(script.get_data_dir(), filename).replace('\\', '/')
        dda = filesys_storage_api.default_dir_data.replace('\\', '/')
        if file_path.startswith(dda):
            file_path = file_path[len(dda):]
        file_path = file_path.lstrip('/')

        datafile_objs[file.filename] = schema.Datafile(
                        script_id=script_id, 
                        device_id=script.device_id, 
                        file_type=file_type, 
                        file_path=file_path,
                        filename=os.path.basename(file_path))
        datafile_objs[file.filename]

    datafile_objs = {k:v for k, v in zip(datafile_objs.keys(), dbi.add_many(list(datafile_objs.values())))}

    return datafile_objs


async def _upload_and_register_files(datafile_objs: Dict[str, schema.Datafile], files: list[UploadFile] = File(...), ret_kwargs=False):
    global serializers

    kwargs = {}
    res = []

    for file in files:
        try:
            assert file.filename in datafile_objs, f'the uploaded file {file.filename=} is not in the corresponding dict of datafile objects! make sure you give a valid datafile_obj for each dict uploaded file!'

            datafile = datafile_objs[file.filename]
            datafile.mime_type = file.content_type
            if datafile.data_type == schema.DATAFILE_TYPE.UNKNOWN: #and not datafile.mime_type is None:
                if 'text' in datafile.mime_type:
                    datafile.data_type = schema.DATAFILE_TYPE.TEXTFILE
                if 'json' in datafile.mime_type:
                    datafile.data_type = schema.DATAFILE_TYPE.JSON
                elif 'pandas' in datafile.mime_type:
                    datafile.data_type = schema.DATAFILE_TYPE.DATAFRAME
                else:
                    datafile.data_type = schema.DATAFILE_TYPE.BINARY

            content_bts = await file.read()

            dfa = None
            for k, v in serializers.items():
                log.info(f'testing serializer {k} on {datafile}')

                if v.test_should_upload(datafile):
                    log.info(f'serializer "{k}" matched for "{datafile}"')
                    dfa = await v.upload(datafile, content_bts)
                else:
                    log.info(f'serializer "{k}" DID NOT MATCH for "{datafile}"')


            if dfa is None:
                raise HTTPException(status_code=400, detail="No storage location was found in the server config to save this data to!")
            
            assert datafile.locations_storage_json, 'seems like nothing was uploaded! (first test!)'

            # print('\n'*10)
            # print(dfa.model_dump())
            # print('\n'*10)

            datafile.status = schema.STATUS_DATAFILE.READY if len(content_bts) > 0 else schema.STATUS_DATAFILE.EMPTY

            kwargs[datafile.id] = {
                'status': datafile.status,
                'locations_storage_json': datafile.locations_storage_json,
                'data_type': datafile.data_type,
                'mime_type': datafile.mime_type
            }

        except FileExistsError as e:
            raise

        except Exception as e:
            log.exception(e)
            s = str(e.res.text) if hasattr(e, 'res') else str(e)
            s = f"ERROR: {s}"
            datafile.append_error_msg(s)
            datafile.status = schema.STATUS_DATAFILE.ERROR
            kwargs[datafile.id] = {'errors': datafile.errors, 'status': datafile.status}

            # raise HTTPException(status_code=500, detail=f"Error uploading data file: {str(e)}")
        res.append(datafile)

    return kwargs if ret_kwargs else res
    
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

@app.get("/qry/script/{script_id}/docs")
async def ids_projectvariable(script_id:int, html:int = Query(default=0, description='anything but 0 and this route will render the doc as HTML instead of returning the JSON representation')):
    with dbi.se() as session:
        script = session.get(schema.Script, script_id)
        if not script:
            raise HTTPException(status_code=404, detail="script not found")
        if html:
            s = '\n'.join([f'<li>{k}: <a href={v}>{v}</a></li>' for k, v in script.docs_json.items()])
            page = f'<ul>{s}</ul>'
            return HTMLResponse(content=page, status_code=200)
        else:
            return script.docs_json
    
    
@app.get("/qry/script/{script_id}/params")
async def ids_projectvariable(script_id:int):
    with dbi.se() as session:
        script = session.get(schema.Script, script_id)
        if not script:
            raise HTTPException(status_code=404, detail="script not found")
        return script.script_params_json


@app.get("/qryq")
async def ids_projectvariable(table:str= Query('either device, datafile, or script'), id:str|int = Query('the id which to query for')):
    assert table in 'device datafile script'.split(), f'kwarg "el_type" must be in either device, datafile, or script, but was {table=} ({type(table)=})'

    with dbi.se() as session:
        if table == 'datafile':
            d = session.get(schema.Datafile, int(id))    
            if not d:
                raise HTTPException(status_code=404, detail=f"datafile with {id=} not found")
            return [d]
        elif table == 'device':
            d = session.get(schema.Device, id)
            if not d:
                raise HTTPException(status_code=404, detail=f"device with {id=} not found")
            return d.datafiles
        elif table == 'script':
            d = session.get(schema.Script, int(id))
            if not d:
                raise HTTPException(status_code=404, detail=f"script with {id=} not found")
            return d.datafiles
        else:
            raise KeyError(f'{table=} is unknown and must be either device datafile or script')
    
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




@app.get("/action/script/{script_id}/trigger_upload")
def action_trigger_upload(script_id:int, is_dryrun:int=Query(default=0, description='if this is anything but 0 it will prevent any actual upload form happening')):
    try:
        log.info(f'trigger_upload for {script_id=}')
        
        script = dbi.get(schema.Script, script_id)
        if not script:
            raise HTTPException(status_code=404, detail=f"Script {script_id=} not found in db")
        
        path = script.get_script_dir()
        dir_path = path.rstrip('/')
        dd = filesys_storage_api.default_dir_data.rstrip('/')
        relPath = dir_path[len(dd):]
        
        assert os.path.exists(dir_path), f'{dir_path=} does not exist for {script_id=}'
        
        
        res = []

        for root, dirs, files in os.walk(dir_path):
            r = root.replace('\\', '/')
            if r.startswith(dd):
                r = r[len(dd):]
            
            for file in files:
                abspath = os.path.join(root, file).replace('\\', '/')
                p = r + '/' + file
                uploaders = list(serializers.keys())
                log.debug(f'uploading {p=} from {abspath=} with {uploaders=}')

                for key, ser in serializers.items():
                    if key == 'local':
                        continue
                    remote_path = ser.mk_full_path(p).replace('\\', '/')

                    uploaded = False
                    if abspath.endswith('.ipynb'):
                        html_exporter = nbconvert.HTMLExporter()
                        html_data, resources = html_exporter.from_filename(abspath)
                        rp = remote_path[:-len('.ipynb')] + '.html'
                        
                        content = html_data.encode()
                    else:
                        log.debug(f'Reading from {abspath}')
                        rp = remote_path
                        with open(abspath, 'rb') as fp:
                            content = fp.read()

                    if not is_dryrun:
                        ser.upload_file_content(rp, content, error_on_exist=False)
                        uploaded = True

                    res.append(dict(serializer=key, abspath=abspath, origin=p, remote_path=rp, uploaded=uploaded))
        
        r = dir_path.replace('\\', '/')
        if r.startswith(dd):
            r = r[len(dd):]
        
        p = r + '/' + 'metadata.json'
        abspath = os.path.join(root, 'metadata.json').replace('\\', '/')
        content = json.dumps(get_script_full(script_id), indent=2, default=schema.json_serial).encode()
        for key, ser in serializers.items():
            if key == 'local':
                continue
    
            rp = ser.mk_full_path(p).replace('\\', '/')
            ser.upload_file_content(rp, content, error_on_exist=False)
            res.append(dict(serializer=key, abspath=abspath, origin=p, remote_path=rp, uploaded=uploaded))

        return {'script_id': script_id, 'is_dryrun': is_dryrun, 'success': True, 'result': res}
    
    except Exception as err:
        if 'HTTP' in str(type(err)):
            log.exception(err)
            log.exception(err.res)
            log.exception(err.res.text)
        else:
            log.exception(err)
        
        raise
    

@app.get("/action/kill/{script_int}")
def kill(script_id:int):
    
    with dbi.se() as session:

        script = session.get(schema.Script, script_id)
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

        script = session.get(schema.Script, script_id)
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

        script = session.get(schema.Script, script_id)
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
            
            obj = session.get(schema.Script, script_id)
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

@app.get("/allfiles")
@app.get("/allfiles/")
async def serve_files():
    s = ''
    s += await list_directory('repo', filesys_storage_api.default_dir_repo, recurse_max = 10, dirlinks=False)
    s += await list_directory('libs', filesys_storage_api.default_dir_libs, recurse_max = 10, dirlinks=False)
    s += await list_directory('loose_docs', filesys_storage_api.default_dir_docs, recurse_max = 10, dirlinks=False)
    s += await list_directory('data', filesys_storage_api.default_dir_data, recurse_max = 10, dirlinks=False)
    return Response(s, media_type="text/html")


@app.get("/files/data/{path:path}")
async def serve_files(path: str = ''):
    return await _serve_files('data', filesys_storage_api.default_dir_data, path)

@app.get("/files/repo/{path:path}")
async def serve_files(path: str = ''):
    return await _serve_files('repo', filesys_storage_api.default_dir_repo, path)

@app.get("/files/libs/{path:path}")
async def serve_files(path: str = ''):
    return await _serve_files('libs', filesys_storage_api.default_dir_libs, path)

@app.get("/files/loose_docs/{path:path}")
async def serve_files(path: str = ''):
    return await _serve_files('loose_docs', filesys_storage_api.default_dir_docs, path)

async def _serve_files(k, base_dir, path):
    file_path = os.path.join(base_dir, path)
    if os.path.isdir(file_path):
        return Response(await list_directory(k, file_path), media_type="text/html")
    elif os.path.isfile(file_path):
        return FileResponse(file_path)
    else:
        raise HTTPException(status_code=404, detail="File or directory not found")

async def list_directory(k, directory_path, recurse_max = 5, is_sub=False, dirlinks=True):
    try:        
        html_content = ''
        li = lambda x: f'<li style="list-style-type: none;">\n   {x}\n</li>\n'
        ul = lambda x: f'<ul>\n   {x}\n</ul>\n'

        if len(directory_path) > 200:
            return li(f'"ERROR PATH TOO LONG: {directory_path}"')
        files = os.listdir(directory_path)

        if not is_sub:
            html_content = f"<h2><strong>\"{k}\"</strong> - Directory:</h2>"
            post = f'  N={len(files)} sub files and folders'
            html_content += '\n\n<ul>\n'
            html_content += li(f'"{directory_path}" ({post})')
            if files:
                html_content += await list_directory(k, directory_path, recurse_max-1, is_sub=True, dirlinks=dirlinks)
            else:
                html_content += "\n\n</ul>\n\n"
            return html_content

        html_content += '<ul>\n'
        for file_name in files:
            file_path = os.path.join(directory_path, file_name)

            if os.path.isdir(file_path):
                N = len(os.listdir(file_path))
                post =  '   (EMPTY)' if N == 0 else ''
                if dirlinks:
                    html_content += li(f'<a href="/files/{k}/{file_path}">{file_name}</a>')
                else:
                    html_content += file_name

                if recurse_max > 0 and N > 0:
                    html_content += await list_directory(k, file_path, recurse_max-1, is_sub=True, dirlinks=dirlinks)
                if is_sub and recurse_max == 0 and N > 0:
                    html_content += ul(li(f'(... N={N} files and folders hidden)'))
                if post:
                    html_content += ul(li(post))
            else:
                html_content += f'<li style="list-style-type: none;"><a href="/show/{file_path}">{file_name}</a></li>'
        html_content += "\n\n</ul>\n\n"

    except Exception as err:
        log.exception(err)
        html_content += f'<pre>{traceback.format_exception(err)}</pre>'


    return html_content


@app.get("/doc/example")
def doc_example(html:int = Query(default=0, description='anything but 0 and this route will render the doc as HTML instead of returning the JSON representation'),
                short:int = Query(default=0, description='set to 1 and this route will not include any image data')):

    pyd.DocBuilder()
        
    doc = pyd.DocBuilder() # basic doc where we always append to the end
    doc = pyd.DocBuilder()
    doc.add_chapter('Introduction')
    doc.add('dummy text which will be added to the introduction')
    doc.add_kw('verbatim', 'def hello_world():\n   print("hello world!")')
    doc.add_chapter('Second Chapter')
    doc.add_kw('markdown', 'This is my fancy `markdown` text for the Second Chapter')
    if not short:
        p = 'static/images/minerva.jpg'
        if os.path.exists(p):
            with open(p) as fp:
                doc.add_image(p)
        else:
            doc.add_image("https://github.githubassets.com/assets/GitHub-Mark-ea2971cee799.png")

    if html:
        return HTMLResponse(content=doc.to_html(), status_code=200)
    else:
        return doc.dump()

class UploadDocSchema(BaseModel):
    doc_name: str = ''
    doc: list[dict]
    force_overwrite:bool = False
    page_title:str = ''


def handle_new_doc(doc:pyd.DocBuilder, doc_name, dir_rep, page_title, force_overwrite):

    if not os.path.exists(dir_rep):
        filesys_storage_api.mkdir(dir_rep)

    dc_local = doc.export_all(dir_path=dir_rep, report_name=doc_name)
    
    localpath = next((k for k in dc_local if k.endswith('html')), None)
    
    baseurl = config.get('globals').get('dbserver_uri')
    local_url = f'{baseurl}/downloadq?path={urllib.parse.quote(localpath)}'

    rmconfig = config.get('wiki_uploader', {}).get('redmine', {})
    project_id = rmconfig.get('project_id')

    if rmconfig and redmine_api.redmine and project_id:
        upload_url = doc.to_redmine_upload(redmine=redmine_api.redmine, 
                                project_id=project_id,
                                report_name=doc_name,
                                page_title=page_title,
                                force_overwrite=force_overwrite,
                                verb=True
                                )
        upload_info = 'success see result link for the report '
        uploaded = True
    else:
        upload_url = ''
        upload_info = 'SKIPPED could not upload because any of "rmconfig and redmine_api.redmine and project_id" failed'
        uploaded = False
        
    return {
        "message": upload_info, 
        "url": upload_url if upload_url else local_url, 
        'dir_rep': dir_rep,
        'local_files': dc_local, 
        'saved_local': True, 
        'saved_remotely': uploaded,
        'local_url': local_url,
        'upload_url': upload_url
    }


@app.post("/doc/upload")
async def doc_upload(r: UploadDocSchema) -> Dict[str, Any]:
    try:
        docreq = r.model_dump() # await r.json()
        assert docreq, 'doc can not be empty!'
        assert docreq.get('doc', [])
        doc_name = docreq.get('doc_name', '')
        doc = pyd.DocBuilder(docreq.get('doc', []))
        if not doc_name:
            doc_name = filesys_storage_api.get_default_doc_name('0', 'no_device')

        dir_rep = filesys_storage_api.default_dir_docs
        res = handle_new_doc(doc, doc_name, dir_rep, docreq.get('page_title', ''), docreq.get('force_overwrite', ''))
        res['ok'] = True
        return res
    
    except Exception as err:
        log.exception(err)
        raise



@app.post("/action/script/{script_id}/upload/doc")
async def upload_doc_for_script(script_id: int, r: UploadDocSchema) -> Dict[str, Any]:
    try:
        docreq = r.model_dump() # await r.json()
        assert docreq, 'doc can not be empty!'
        assert docreq.get('doc', [])
        doc_name = docreq.get('doc_name', '')
        doc = pyd.DocBuilder(docreq.get('doc', []))

        with dbi.se() as session:
            script = session.get(schema.Script, script_id)
            if not script:
                raise HTTPException(status_code=404, detail="Script not found")
            
            
            if not doc_name:
                device_id = script.device_id if script.device_id else 'no_device'
                doc_name = filesys_storage_api.get_default_doc_name(script_id, device_id)

            dir_rep = script.get_reports_dir()

            res = handle_new_doc(doc, doc_name, dir_rep, docreq.get('page_title', ''), docreq.get('force_overwrite', ''))
            docs_json = script.docs_json

            docs_json[f'local/{doc_name}'] = res.get('local_url', '')
            if res.get('upload_url', ''):
                docs_json[f'remote/{doc_name}'] = res.get('upload_url', '')
                
            dbi.set_property(schema.Script, script_id, docs_json=docs_json)

        res['script'] = dbi.get(schema.Script, script_id)
        res['script_id'] = script_id
        res['ok'] = True
        return res
    
    except Exception as err:
        log.exception(err)
        raise


class UserFeedbackRequest(BaseModel):
    message: str
    request_type: str
    id: str
    script_id: int|None = None

class UserFeedbackReply(BaseModel):
    id: str
    message: str
    response_type: str
    files: dict[str, str]|None = None


@app.post("/user_feedback/create")
async def user_feedback_create(req: UserFeedbackRequest)-> Dict[str, Any]:

    id = req.id
    global feedback_requests, feedback_answers
    if id in feedback_requests:
        raise HTTPException(400 , f'request with {id=} already exists!')
    
    feedback_requests[id] = req        
    return {'success': True, 'id': req.id, 'request': feedback_requests.get(id, None)}

@app.get("/user_feedback/get")
async def user_feedback_get(id = Query(description='The id of the request to wait for', default=None))-> Dict[str, Any]:

    global feedback_requests, feedback_answers

    if id is None:
        r = {id:feedback_requests.get(id, None) for id in feedback_requests}
        # if not r:
        #     id_ = 'dummy_request'
        #     return {id_: UserFeedbackRequest(id=id_, message='There is currently no request on the server to handle... please check again later', request_type='')}
        
        return r

    if not id in feedback_requests:
        raise HTTPException(404 , f'request with {id=} was not found!')
    
    return {'request': feedback_requests.get(id, None), 'answer': feedback_answers.get(id, None)}


@app.get("/user_feedback/wait_completed")
async def user_feedback_wait_completed(id = Query(description='The id of the request to wait for'))-> Dict[str, Any]:
    raise NotADirectoryError('blocking until ready is currently buggy. Please use a polling mechanism with "/user_feedback/check?id=..." instead')
    if not id in feedback_requests:
        raise HTTPException(404 , f'request with {id=} was not found!')
    
    while not feedback_answers.get(id, None):
        time.sleep(1)

    return {'request': feedback_requests.pop(id), 'answer': feedback_answers.pop(id)}



@app.get("/user_feedback/check")
async def user_feedback_wait_completed(id = Query(description='The id of the request to wait for'))-> Dict[str, Any]:
    if not id in feedback_requests:
        raise HTTPException(404 , f'request with {id=} was not found!')
    if not id in feedback_answers:
        return {}
    else:
        return {'request': feedback_requests.pop(id), 'answer': feedback_answers.pop(id)}


@app.post("/user_feedback/create_and_wait")
async def user_feedback_create_and_wait(req: UserFeedbackRequest, request: Request)-> Dict[str, Any]:
    raise NotADirectoryError('blocking until ready is currently buggy. Please use a polling mechanism with "/user_feedback/check?id=..." instead')
    log.info(f'{request.client} requested {req=} and will wait for it')

    id = req.id
    global feedback_requests, feedback_answers
    if id in feedback_requests:
        raise HTTPException(400 , f'request with {id=} already exists!')
    feedback_requests[id] = req 

    while not feedback_answers.get(id, None):
        await asyncio.sleep(1)

    return {'request': feedback_requests.pop(id), 'answer': feedback_answers.pop(id)}


@app.post("/user_feedback/reply")
async def user_feedback_reply(request: Request):#, files: list[UploadFile] = File(...)):
    
    global feedback_requests, feedback_answers

    res = False
    form = await request.form()
    message = form.get("message")
    success = form.get("success")
    id_ = form.get("id")

    client = f'{request.client.host}:{request.client.port}'

    files = []
    file_names = [file.filename for file in files]
    s = '"confirmation"' if success else '"cancle"'
    response_text = f"Received {s} reply.\n\n{message}\n\n"
    if file_names:
        response_text += f" and files: {file_names}\n\n"
    response_text += f' from {client=}'

    input_data = {
        'message': message,
        'id': id_, 
        'success': success, 
        'files': file_names, 
        'sender': client,
        'time': helpers.iso_now(),
    }

    if id_ in feedback_requests and feedback_answers:
        response_text += f'\n\nRESULT: The request with ID={id_} is already marked as finished!'
    elif id_ in feedback_requests:
        res = True
        response_text += f'\n\nRESULT: marked request with ID={id_} as finished'
        feedback_answers[id_] = input_data
    else:
        response_text += f'\n\nRESULT: The request with ID={id_} does not exist or nobody is waiting for it any more!'
    

    

    return {"response": response_text, 'id': id_, 'success': res, 'input_data': input_data}


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