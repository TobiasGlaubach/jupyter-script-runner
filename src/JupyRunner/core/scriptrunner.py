import datetime
import hashlib
import json
import time
import papermill
import nbconvert
import os

from JupyRunner.core import schema, api_interface
from JupyRunner.core.schema import Script, STATUS
from JupyRunner.core.helpers import log, get_utcnow, make_zulustr, now_iso
from JupyRunner.core import helpers_mattermost

import traceback

config = None
url = None
api = None
full_api = None
var_api = None
dfi_api = None
device_api = None

def send_mattermost_failed(script:Script, err: Exception):
    s = ''
    s += f'\nFAILED on post processing for script {script.id=} and {script.script_out_path=}'
    s += f'\nError Message: ```{str(err)}```'
    s += f'\nSTATUS NEW: **FAILED**'
    helpers_mattermost.send_mattermost(s)

def send_mattermost_status(script:Script):
    helpers_mattermost.send_mattermost(f'{script.id=} {script.status=}')

def setup(cnfg):
    api_interface.setup(cnfg)
    helpers_mattermost.setup(cnfg)

    global config, api, full_api, var_api, dfi_api, device_api
    config = cnfg

    
    url = config['globals']['dbserver_uri']
    log.info(f'Scriptrunner initialized with {url=}')
    api = api_interface.ScriptClient(url)
    dfi_api = api_interface.DataFileClient(url)
    device_api = api_interface.DeviceClient(url)
    var_api = api_interface.ProjectVariableClient(url)
    full_api = api_interface.APIClient(url)

def start(cnfg):
    api_interface.start(cnfg)
    helpers_mattermost.start(cnfg)

    global config
    config = cnfg


def get(script_id) -> schema.Script:
    return api.get(script_id)

def commit(script:schema.Script) -> schema.Script:
    return api.put(script)

def set_prop_remote(script_id, **kwargs) -> schema.Script:
    if hasattr(script_id, 'id'):
        script_id = script_id.id
    return api.patch(script_id, **kwargs)

def prepare_for_run(script:Script):
    script, _ = _pre(script, is_test=False)
    return script

def _pre(script:Script, is_test=False):
    
    if not is_test:
        log.info("Script %d: setting default fields", script.id)
    
    script.set_script_name()
    script.set_script_version()
    script.set_script_out_path()
    if not is_test:
        script = commit(script)

    if not is_test:
        # Convert script to dictionary
        log.info("Script %d: Converting to dictionary", script.id)
    
    all_params = {'dbserver_uri': url, 'url': url}
    all_params = script.model_dump()

    if not is_test and script.device_id:
        all_params['device'] = device_api.get(script.device_id).model_dump()
    else:
        all_params['device'] = []

    if not is_test and script.id:
        all_params['datafiles'] = full_api.get(f'qry/script/{script.id}/datafiles')
    else:
        all_params['datafiles'] = []

    if not is_test:
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(script.script_out_path)
        os.makedirs(output_dir, exist_ok=True)
        log.info("Script %d: Created output directory if needed: %s", script.id, output_dir)

    # Extract and merge parameters
    all_params['script_id'] = all_params.pop("id")
    params_json = all_params.pop("script_params_json")
    if not 'follow_up_script' in params_json:
        params_json['follow_up_script'] = {'script_in_path': '', 'script_params_json': {}}
    
    all_params.update(params_json)


    # sanitize
    all_params = json.loads(json.dumps(all_params, default=schema.json_serial))
    log.info("Script %d: Extracted and merged parameters", script.id)

    return script, all_params

def pre_check(script:Script):
    dummy_script = Script(**script.model_dump())
    dummy_script.id = time.time_ns()
    dummy_script.comments += 'this is a dummy script automatically generated for testing'
    _pre(dummy_script, is_test=True)
    return dummy_script

def init_follow_up_script(script):
    
    fus_dc = script.script_params_json.get('follow_up_script', {})
    if fus_dc and fus_dc.get('script_in_path'):
        log.info('Addinf follow up script after {script.id=}!')

        if 'data_json' in fus_dc:
            fus_dc['data_json'].update({'parent_script_id': script.id})
        else:
            fus_dc['data_json'] = {'parent_script_id': script.id}                        
        fus = api.post(fus_dc)
        return fus
    
    return None

def run_script(script_id:int):
    """
    Runs a Jupyter script using Papermill and converts the output to HTML.

    Args:
        script: The Script id.

    Returns:
        The path to the generated HTML file, or None on error.
    """

    try:
        script = get(script_id)

        log.info("Script %d: Starting", script.id)
        

        script = set_prop_remote(script, status = STATUS.STARTING)

        script, all_params = _pre(script, is_test=False)
        
        log.info("Script %d: Running", script.id)
        script = set_prop_remote(script, status = STATUS.RUNNING, time_started = get_utcnow())

        
        helpers_mattermost.send_mattermost(f'Script {script.id}: RUNNING with:  {script.script_in_path} (VER:{script.script_version}) -> {script.script_out_path}')
        # Run the script using Papermill
        nb = papermill.execute_notebook(
            script.script_in_path,
            script.script_out_path,
            parameters=all_params,
            kernel_name="python3"
        )

        log.info(f"Script {script.id}: Finished running with Papermill", script.id)

        # Set script status to FINISHING
        script = set_prop_remote(script, status = STATUS.FINISHING)
        log.info("Script %d: Finishing on", script.id)

        # Convert the output notebook to HTML
        html_exporter = nbconvert.HTMLExporter()
        html_data, resources = html_exporter.from_filename(script.script_out_path)
        new_out = script.script_out_path.replace(".ipynb", ".html")
        with open(new_out, "w", encoding='utf-8') as f:
            f.write(html_data)
        script.script_out_path = new_out
        script.time_finished = get_utcnow()

        script.papermill_json = nb.get('metadata', {}).get('papermill', {})
        err = nb.get('exception', '')


        if err:
            script.status = STATUS.FAILED
            script.errors += now_iso() + ' | ' + str(err)
            send_mattermost_failed(script, err)
            s = f"Script {script.id}: Finished with ERROR on {make_zulustr(script.time_finished)}"
            log.error(s)
        else:
            # Set script status to FINISHING
            script.status = STATUS.FINISHED
            script.script_out_path = script.script_out_path.replace(".ipynb", ".html")
            s = f"Script {script.id}: Finished successfully on {make_zulustr(script.time_finished)}"
            log.info(s)
            helpers_mattermost.send_mattermost(s)

        script = commit(script)

        return script

    except Exception as e:
        raise
        log.error("Script %d: Error running script: %s", script.id, str(e))
        script.status = STATUS.ERROR
        script.append_error_msg(traceback.format_exc())  # Store traceback info
        commit(script)
        send_mattermost_failed(script, e)
        return None  # Indicate error