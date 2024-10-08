
#!/usr/bin/python3
""" 
the processing core to run jupyter notebooks in papermill
"""

import datetime
import subprocess
import shutil
import sys, os
import time
import traceback

import yaml

if __name__ == '__main__':
    # add to path for testing
    import sys, inspect, os
    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, parent_dir)

from JupyRunner.core import schema, filesys_storage_api
from JupyRunner.core import scriptrunner as runner

from JupyRunner.core.helpers import get_utcnow, make_zulustr, parse_zulutime, log, set_loglevel, get_primary_ip
from JupyRunner.core.helpers_mattermost import send_mattermost

my_runner_id = os.environ.get('RUNNER_ID', None)

config =  None
run_directly = None

processes = {}

with open('config.yaml', 'r') as fp:
    config = yaml.safe_load(fp)

modules = [runner, filesys_storage_api]
for module in modules:
    module.setup(config)

for module in modules:
    module.start(config)

set_loglevel(config)


api = runner.api
run_directly = config.get('procserver', {}).get('do_direct_running', 0)

commit = runner.commit
set_prop_remote = runner.set_prop_remote

def get_script(script_id:int) -> schema.Script:
    if isinstance(script_id, str):
        script_id = int(script_id)
    return api.get(script_id)


def test_shall_I_run_this_script(script, by_ip=False):

    
    dc = script.data_json

    if by_ip:
        req_runner_id = dc.get('runner_ip', dc.get('runner_id', None))
        _my_runner_id = get_primary_ip()
    else:
        req_runner_id = dc.get('runner_id', None)
        _my_runner_id = my_runner_id

    if _my_runner_id is None: # default runner
        if req_runner_id is None: # no specific runner needed
            return True # --> can run
        else:
            return False # --> specific runner needed
    else: # specific runner
        if req_runner_id is None:
            return False # --> default runner should run the script, not me
        elif req_runner_id == _my_runner_id:
            return True # --> yep I am the one who should run this
        else:
            return False # --> nope someone else should run this





def get_running_processes():
    return [ get_script(int(key)) for key in processes.keys()]


def test_is_running(key):
    if key in processes:
        return_code = processes[key].poll() 
        return return_code is None
    else:
        return False

def test_is_started(key):
    return key in processes

def finish(p, id):
    log.info(f'{id} DONE. returncode:{p.returncode}')
    retcode = p.poll()
    out, err = p.communicate()
    
    out = out.decode(sys.stdout.encoding)
    err = err.decode(sys.stderr.encoding)

    obj = get_script(id)
    if retcode:
        obj.append_error_msg(err)
        log.error('ERROR: ' + err)
        log.debug('setting status: FAILED...' )
        obj = set_prop_remote(id, status = schema.STATUS.FAILED, errors = obj.errors)

        s = ''
        s += f'\nFAILED on processing for script {id}'
        s += f'\nError Message: ```{str(err)}```'
        s += f'\nSTATUS NEW: **FAILED**'
        send_mattermost(s)

    return id


def start_job(id):

    assert id not in processes, f'cannot start job {id=} since it is still running!'
    assert id, 'need to give an id!'
    run_script_path = config['procserver']['run_script_path']
    
    cmds = [run_script_path, '--id', str(id)]
    if os.name == 'nt':
        cmds = [config['procserver']['pythonpath_for_win']] + cmds
    else:
        cmds = ['python'] + cmds

    s = ' '.join(cmds)
    log.info(f'RUNNING... "{s}"')
    if os.name == 'nt' and 'TESTING' in config and config['TESTING']:
        p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
    processes[id] = p

def cancle_job(id):
    if not test_is_running(id):
        return 404, {'ERROR': 'no such job found within running jobs'}
    else:
        p = processes[id]
        p.terminate()
        p.wait(timeout=config['procserver']['terminate_timeout_sec'])
        p.kill()
        out, err = p.communicate()
        out = out.decode(sys.stdout.encoding)
        err = err.decode(sys.stderr.encoding)
        
        obj = get_script(id)
        obj.append_error_msg(err)
        obj = set_prop_remote(obj, status = schema.STATUS.CANCELLED, errors = obj.errors)
        
        del processes[id]



def tick_awaiting_check():
    # initial checks
    log.debug(f'tick_awaiting_check...')

    stati = [schema.STATUS.INITIALIZING, schema.STATUS.AWAITING_CHECK]
    scripts = api.qry(stati=stati)
    log.debug(f'got N={len(scripts)} scripts which need attention...')

    for script in scripts:
        try:
            log.info('CHECKING for ' + str(script))

            
            log.debug('checking...')
            runner.pre_check(script)
            
            log.debug('actually setting...')
            script = runner.prepare_for_run(script)
            stat = schema.STATUS.WAITING_TO_RUN
            log.debug(f'   FROM: {script.script_in_path}')
            log.debug(f'     TO: {script.script_out_path}')

        except Exception as err:
            
            script.append_error_msg(str(err))
            log.error('ERROR: ' + str(err))
            stat = schema.STATUS.FAULTY
        
        script.status = stat

        log.info(f'DONE CHECKING with {script.id} --> {stat}')

        script = commit(script)
        

def tick_cancelling():
    log.debug(f'tick_cancelling...')
    # initial checks
    stati = [schema.STATUS.CANCELLING]
    scripts = api.qry(stati=stati)
    log.debug(f'got N={len(scripts)} scripts which need attention...')

    for script in scripts:
        try:
            if test_is_running(script.id):
                cancle_job(script.id)
            stat = script.status
        except Exception as err:
            script.append_error_msg(str(err))
            log.error('ERROR: ' + str(err))
            stat = schema.STATUS.FAULTY
        
        log.debug('setting status... ' + stat)
        script = set_prop_remote(script, status=stat, errors=script.errors)

        log.info('DONE CHECKING with ' + str(script))
        


def tick_cleanup():
    log.debug(f'tick_cleanup...')
    # clean up if finished
    to_remove = []
    for script_id, p in processes.items():
        try:
            
            if not test_is_running(script_id):
                log.info(f'CLEANING UP PROCESSES for script {script_id}, {p}')
                k = finish(p, script_id)
                to_remove.append(k)
                log.info(f'DONE CLEANING script {script_id}, {p}')

        except Exception as err:
            obj = get_script(script_id)
            obj.append_error_msg(err_msg=str(err))
            log.exception(f'ERROR while cleaining up {key}, {p}')
            log.exception('ERROR: ' + str(err))
            set_prop_remote(obj, status=schema.STATUS.FAULTY, errors=obj.errors)
    
    for key in to_remove:
        removed = processes.pop(key)
        log.debug('removed: ' + str(removed) )
        

def tick_start():
    log.debug(f'tick_start...')
    stati = [schema.STATUS.STARTING, schema.STATUS.WAITING_TO_RUN]
    stat = None
    scripts = api.qry(stati=stati)
    log.debug(f'got N={len(scripts)} scripts which need attention...')
    for script in scripts:
        try:
            key = script.id

            if not test_is_running(key) and \
                script.test_for_start_condition() and \
                    (test_shall_I_run_this_script(script) or test_shall_I_run_this_script(script, by_ip=True)):
                
                log.info('STARTING PROCESSING for ' + str(script))
                log.debug('setting status... ' + schema.STATUS.STARTING)
                script = set_prop_remote(script, status = schema.STATUS.STARTING)
                assert script.status == schema.STATUS.STARTING
                
                if run_directly:
                    runner.run_script(script.id)
                    log.info('DONE RUNNING with ')
                    runner.init_follow_up_script(script)
                    
                else:
                    start_job(script.id)

                    log.info('DONE STARTING with ' + str(script))
            else:
                log.debug('test_is_running:          ' + str(test_is_running(key)))
                log.debug('test_for_start_condition: ' + str(script.test_for_start_condition()))
                
        except Exception as err:

            traceback.print_exception(err)
            script.append_error_msg(str(err))
            log.error('ERROR: ' + str(err))
            stat = schema.STATUS.FAULTY
            log.error('setting status... ' + stat)
            script = set_prop_remote(script.id, status=stat, errors=script.errors)
            
            assert script.status == schema.STATUS.FAULTY, f'status was not set to faulty! but is {script.status=}'
            script = api.get(script.id)
            assert script.status == schema.STATUS.FAULTY, f'status was not set to faulty! but is {script.status=}'

        log.debug(f'tick_start...DONE with script={script.id} {script.status=}')

    

def tick():
    log.debug(f'tick... ')
    tick_awaiting_check()
    tick_cancelling()
    tick_cleanup()
    tick_start()
    log.debug(f'tick... DONE')

def startup_testrun():
    dummy_device = runner.device_api.get('dummy_device')
    if dummy_device is None:
        dummy_device = schema.Device(id='dummy_device', address='http://localhost:8080', connection_protocol='http', comments='a dummy device for testing')
        dummy_device = runner.device_api.put(dummy_device)

    p = '/home/jovyan/99_startup_testscript.ipynb'
    assert os.path.exists(p), 'startup testscript is missing! >> '  + p
    new_path = filesys_storage_api.default_dir_repo + '/' + os.path.basename(p)
    shutil.move(p, new_path)

    startup_script = runner.api.post({'script_in_path': new_path, 'device_id': 'dummy_device'})
    assert startup_script, 'error starting a testscript!'



def startup_info():
    id = 'pc_default_startinfo' if not my_runner_id else f'pc_{my_runner_id}_startinfo'
    procserver_info = runner.var_api.get(id)
    data = {
        'filesys': filesys_storage_api.get_folderinfo(), 
        't_started': make_zulustr(get_utcnow()), 
        'cwd': os.getcwd(), 
        '__file__': __file__,
        'runner_id': my_runner_id,
        'ip': get_primary_ip(),
    }

    if procserver_info is None:
        procserver_info = schema.ProjectVariable(id=id, data_json={})

    procserver_info.data_json = data
    runner.var_api.put(procserver_info)


def update_ticker(t_sleep):
    procserver_info = runner.var_api.get('procserver_info')
    if procserver_info is None:
        log.info('FIRST TICK EVER!')
        procserver_info = schema.ProjectVariable(id='procserver_info', data_json={'t_last': None, 't_expected_next': '', 'running_processes': []})
    

    t_last = get_utcnow()
    procserver_info.data_json['t_last'] = make_zulustr(t_last)
    procserver_info.data_json['t_expected_next'] = make_zulustr(t_last + datetime.timedelta(t_sleep))
    procserver_info.data_json['running_processes'] = [dict(script_id=k, pid=v.pid) for k, v in processes.items()]
    
    runner.var_api.put(procserver_info)


def run():
    log.info('procserver starting up!')
    t_sleep = config.get('procserver', {}).get('t_interval', 60)
    
    i = 0
    t = t_sleep/2
    log.info(f'procserver waiting {t=} sec before starting...')
    time.sleep(t) # to have the DB up and running
    log.info(f'pinging server at "{api.base_url}"...')

    assert runner.api_interface.ping(), f'pinging {runner.api_interface.url=} failed!'
    log.info('ping OK!')

    startup_info()
    
    startup_testrun()

    while(1):
        try:
            if i % 100 == 0:
                log.info('procserver is still alive!')
                update_ticker(t_sleep)

            tick()
            i += 1

        except Exception as err:
            log.error(err)
            traceback.print_exception(err)

            

        time.sleep(t_sleep)

if __name__ == '__main__':
    log.info('STARTING procserver!')

    

    if len(sys.argv) >1 and 'debug' in sys.argv[-1].lower():

        log.setLevel('DEBUG')
        dc = {
            # "script_in_path": r"C:\Users\tglaubach\repos\jupyter-script-runner\src\scripts\00_example_script.ipynb".replace('\\', '/'),
            "script_in_path": r"C:\Users\tglaubach\repos\jupyter-script-runner\src\scripts\02_example_functional_test.ipynb".replace('\\', '/'),
            "script_params_json": { "do_upload": 1 }
            # ... other script attributes
        }
        api.post(dc)
        tick()

    elif len(sys.argv) > 1:
        my_runner_id = sys.argv[-1]
        run()
    else:
        run()