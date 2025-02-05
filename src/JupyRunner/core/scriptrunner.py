import datetime
import hashlib
import json
import time
import papermill
import nbconvert
import os

import yaml

import pydocmaker as pyd

from JupyRunner.core import schema, api_interface, filesys_storage_api
from JupyRunner.core.schema import Script, STATUS
from JupyRunner.core.helpers import log, get_utcnow, make_zulustr, now_iso, logging, limit_len
from JupyRunner.core.helpers_mattermost import send_mattermost, LOGGING_EMOJIES
from JupyRunner.core import helpers_mattermost

import traceback

config = None
url = None
api = None
full_api = None
var_api = None
dfi_api = None
device_api = None

from JupyRunner.client import api_accessor as capi


# Create a custom log handler
class CustomHandler(logging.Handler):

    def emit(self, record):
        # Call the function with the log message
        message = self.format(record)
        outfile = getattr(self, 'outfile', '')
        if outfile:
            with open(outfile, 'a+') as fp:
                fp.write('\n')
                fp.write(message)
        else:
            print(message)


def send_mattermost_failed(script:Script, err: Exception):
    s = f'{script.get_device_link_md()} | {script.get_link_md()} | {script.get_showpath_md()} | STATUS=**{script.status}** => Error: ```{limit_len(err, 50)}```'
    send_mattermost(s, emoji=LOGGING_EMOJIES.FAIL)
    return s

def send_mattermost_status(script:Script, post_str='', emoji=None):
    if emoji:
        pass
    elif script.is_failed():
        emoji = LOGGING_EMOJIES.FAIL
    elif script.status == STATUS.FINISHED:
        emoji = LOGGING_EMOJIES.SUCCESS
    else:
        emoji = LOGGING_EMOJIES.EMPTY
    s = f'{script.get_device_link_md()} | {script.get_link_md()} | {script.get_showpath_md()} | STATUS=**{script.status}** {post_str}'.strip()
    send_mattermost(s, emoji = emoji)
    return s

def send_userlog(msg, script, color='grey', doc = None):
    try:
        if isinstance(doc, str):
            d = pyd.Doc()
            d.add_md(doc)
            doc = d
        filename_without_extension = os.path.splitext(os.path.basename(script.script_out_path))[0]

        api_log = capi.ServerApi(config.get('globals', {}).get('dbserver_uri'))
        api_log.user_info(f'Scriptrunner: {msg}', color=color, script_id=script.id, script_name=filename_without_extension, device_id=script.device_id, doc=doc)
    except Exception as err:
        pass


def setup(cnfg):
    api_interface.setup(cnfg)
    helpers_mattermost.setup(cnfg)

    global config, api, url, full_api, var_api, dfi_api, device_api
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
        log.info(f"Script {script.id}: setting default fields", )
    
    script.set_script_name()
    script.set_script_version()
    script.set_script_out_path()
    if not is_test:
        script = commit(script)

    if not is_test:
        # Convert script to dictionary
        log.info(f"Script {script.id}: Converting to dictionary")
    
    assert url, f"ERROR was setup called properly? the dbserver url is None! {url=}"
    path_to_libs = config.get('pathes', {}).get('default_dir_libs')
    all_params = {'path_to_libs': path_to_libs, 'dbserver_uri': url, 'url': url}
    all_params.update(script.model_dump())

    assert all_params.get('path_to_libs'), f"'path_to_libs' not found or empty in {all_params=}"

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
        log.info(f"Script {script.id}: Created output directory if needed: {output_dir}")

    # Extract and merge parameters
    all_params['script_id'] = all_params.pop("id")
    params_json = all_params.pop("script_params_json")
    if not 'follow_up_script' in params_json:
        params_json['follow_up_script'] = {'script_in_path': '', 'script_params_json': {}}
    
    all_params.update(params_json)


    # sanitize
    all_params = json.loads(json.dumps(all_params, default=schema.json_serial))
    log.info(f"Script {script.id}: Extracted and merged parameters")

    return script, all_params

def pre_check(script:Script):
    dummy_script = Script(**script.model_dump())
    dummy_script.id = time.time_ns()
    dummy_script.comments += 'this is a dummy script automatically generated for testing'
    res, _ = _pre(dummy_script, is_test=True)
    return res

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
        script = get(int(script_id))

        log.info(f"Script {script.id}: Starting")
        send_userlog(f"Starting...", script)

        script = set_prop_remote(script, status = STATUS.STARTING)

        script, all_params = _pre(script, is_test=False)
        
        p_path = os.path.join(script.get_script_dir(), 'parameters.yaml')
        
        # Write all_params as a yaml file to the path given in p_path
        with open(p_path, 'w') as file:
            yaml.dump(all_params, file)

        log.info(f"Script {script.id}: Running")
        
        time.sleep(0.1)
        script = set_prop_remote(script, status = STATUS.RUNNING, time_started = get_utcnow())
        assert script.status == STATUS.RUNNING, 'status was not set to running!'
        
        md = f'{script.get_device_link_md()} | {script.get_link_md()} | {script.get_showpath_md()} | STATUS=**RUNNING**'
        send_mattermost(md, emoji=':black_right_pointing_triangle_with_double_vertical_bar: ')

        doc = pyd.Doc()
        doc.add_md(md)
        send_userlog(f"Running...", script, doc=md)

        # Set up a logger
        pm_logger = logging.getLogger('papermill')
        pm_logger.setLevel(logging.INFO)

        # Create a custom handler
        handler = CustomHandler()
        handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S%z'))
        
        # time = datetime.datetime.utcnow().strftime(filesys_storage_api.timeformat_str)

        handler.outfile = os.path.join(script.get_script_dir(), 'papermill_logs.txt')

        # Add the handler to the logger
        pm_logger.addHandler(handler)

        if script.script_out_path.endswith('.html'):
            log.info('renaming script_out_path to ipynb filetype!')
            script.script_out_path = script.script_out_path[:-len('.html')] + '.ipynb'

        # Run the script using Papermill
        try:
            pm_logger.info(f'SCRIPTRUNNER: starting with {script.id=} {script.status=}\n\n' + '='*200)

            nb = papermill.execute_notebook(
                script.script_in_path,
                script.script_out_path,
                parameters=all_params,
                progress_bar=False,
                log_output=True,
                kernel_name="python3"
            )
        except (papermill.exceptions.PapermillExecutionError) as e:
            err = ''.join(traceback.format_exception(e, limit=3))

            nb = {
                    'metadata': {
                        'papermill': {
                            'exception': str(err),
                        }
                    }
                }
            log.error(err)
            log.debug(traceback.format_exc())

        log.info(f"Script {script.id}: Finished running with Papermill")

        # Set script status to FINISHING
        script = set_prop_remote(script, status = STATUS.FINISHING)
        log.info(f"Script {script.id}: Finishing on")

        # Convert the output notebook to HTML
        html_exporter = nbconvert.HTMLExporter()

        log.info(f"Script {script.id}: Converting to HTML...")
        out_path = script.script_out_path
        html_data, resources = html_exporter.from_filename(out_path)
        new_out = out_path.replace(".ipynb", ".html")
        with open(new_out, "w", encoding='utf-8') as f:
            f.write(html_data)
        log.info(f"Script {script.id}: Converting to HTML...DONE")
        script.script_out_path = new_out

        log.info(f"Script {script.id}: Converting to HTML (without code)...")
        # convert to html without the code and add the result as a document to the script        
        html_exporter.exclude_input = True
        new_out = out_path.replace(".ipynb", "_clean.html")
        html_data, resources = html_exporter.from_filename(out_path)
        with open(new_out, "w", encoding='utf-8') as f:
            f.write(html_data)

        url = f'/show/{new_out}'
        script.docs_json[os.path.basename(url)] = url
        log.info(f"Script {script.id}: Converting to HTML (without code)... DONE")

        script.time_finished = get_utcnow()

        script.papermill_json = nb.get('metadata', {}).get('papermill', {})
        err = nb.get('exception', '')

        if err:
            script.status = STATUS.FAILED
            script.errors += now_iso() + ' | ' + str(err)
            md = send_mattermost_failed(script, err)
            s = f"Script {script.id}: Finished with ERROR on {make_zulustr(script.time_finished)}"
            log.error(s)
            send_userlog(s, script, doc=md)

        else:
            # Set script status to FINISHING
            script.status = STATUS.UPLOADING
            script.script_out_path = script.script_out_path.replace(".ipynb", ".html")
            md = send_mattermost_status(script, emoji=':arrow_up: ')
            send_userlog(f"Statusupdate...", script, doc=md)

        script = commit(script)

        log.info(f'starting uploading {script.id=}')
        res = full_api.get(f'action/script/{script.id}/trigger_upload', params={'is_dryrun': 0})
        
        assert isinstance(res, dict) and res.get('success', False), f'trigger_upload for {script.id=} failed! {res=}'

        script = set_prop_remote(script.id, status=STATUS.FINISHED)
        post = ':warning: :no_entry: **WITH ERRORS** :no_entry: :warning:' if script.errors else ''

        md = send_mattermost_status(script, post_str=post)
        send_userlog(f"Finished...", script, doc=md)

        log.info(f'finished uploading {script.id=} {script.status=}')
        post = ' WITH ERRORS!!!\n' if script.errors else ''
        post += '\n\n' + '='*200
        pm_logger.info(f'SCRIPTRUNNER: finished with {script.id=} {script.status=}' + post)

        return script

    except Exception as e:
        log.error(f"Script {script.id}: Error running script: {e}")
        script.status = STATUS.FAULTY
        script.append_error_msg(traceback.format_exc())  # Store traceback info
        commit(script)
        md = send_mattermost_failed(script, e)
        send_userlog(f"Finished...", script, doc=md)

        return None  # Indicate error