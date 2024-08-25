import datetime
import hashlib
import papermill
import nbconvert
import os

from JupyRunner.core import schema, db_interface
from JupyRunner.core.schema import Script, STATUS
from JupyRunner.core.helpers import log, get_utcnow, make_zulustr, now_iso
from JupyRunner.core.helpers_mattermost import send_mattermost

import traceback

def send_mattermost_failed(script:Script, err: Exception):
    s = ''
    s += f'\nFAILED on post processing for script {script.id=} and {script.script_out_path=}'
    s += f'\nError Message: ```{str(err)}```'
    s += f'\nSTATUS NEW: **FAILED**'
    send_mattermost(s)

def send_mattermost_status(script:Script):
    send_mattermost(f'{script.id=} {script.status=}')


def pre_test(script:Script):
    Script(**script.model_dump())

def _pre(script:Script, is_test=False):
    if not is_test:
        # Set script status to STARTING
        log.info("Script %d: Starting", script.id)
    script.status = STATUS.STARTING
    if not is_test:
        script = db_interface.commit(script)

    if not is_test:
        log.info("Script %d: setting default fields", script.id)
    script.time_started = get_utcnow()
    script.set_script_version()
    script.set_script_out_path()
    if not is_test:
        script = db_interface.commit(script)

    if not is_test:
        # Convert script to dictionary
        log.info("Script %d: Converting to dictionary", script.id)
    all_params = script.model_dump()

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
    if not is_test:
        log.info("Script %d: Extracted and merged parameters", script.id)

    # Set script status to RUNNING
    if not is_test:
        log.info("Script %d: Running", script.id)
    script.status = STATUS.RUNNING
    if not is_test:
        script = db_interface.commit(script)

    return script

def run_script(script: Script):
    """
    Runs a Jupyter script using Papermill and converts the output to HTML.

    Args:
        script: The Script object.

    Returns:
        The path to the generated HTML file, or None on error.
    """

    try:
        # Set script status to STARTING
        log.info("Script %d: Starting", script.id)
        script.status = STATUS.STARTING
        script = db_interface.commit(script)

        log.info("Script %d: setting default fields", script.id)
        script.time_started = get_utcnow()
        script.set_script_version()
        script.set_script_out_path()
        script = db_interface.commit(script)


        # Convert script to dictionary
        log.info("Script %d: Converting to dictionary", script.id)
        all_params = script.model_dump()

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
        log.info("Script %d: Extracted and merged parameters", script.id)

        # Set script status to RUNNING
        log.info("Script %d: Running", script.id)
        script.status = STATUS.RUNNING
        script = db_interface.commit(script)

        send_mattermost(f'Script {script.id}: RUNNING with:  {script.script_in_path} (VER:{script.script_version}) -> {script.script_out_path}')
        # Run the script using Papermill
        nb = papermill.execute_notebook(
            script.script_in_path,
            script.script_out_path,
            parameters=all_params
        )

        log.info(f"Script {script.id}: Finished running with Papermill", script.id)

        # Set script status to FINISHING
        script.status = STATUS.FINISHING
        script = db_interface.commit(script)
        log.info("Script %d: Finishing on", script.id)

        # Convert the output notebook to HTML
        html_exporter = nbconvert.HTMLExporter()
        html_data, resources = html_exporter.from_filename(script.script_out_path)
        new_out = script.script_out_path.replace(".ipynb", ".html")
        with open(new_out, "w") as f:
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
            
            script = db_interface.commit(script)
            s = f"Script {script.id}: Finished successfully on {make_zulustr(script.time_finished)}"
            log.info(s)
            send_mattermost(s)
        return script.script_out_path

    except Exception as e:
        log.error("Script %d: Error running script: %s", script.id, str(e))
        script.status = STATUS.ERROR
        script.error = traceback.format_exc()  # Store traceback info
        script = db_interface.commit(script)
        send_mattermost_failed(script, e)
        return None  # Indicate error