
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

from JupyRunner.core import schema, filesys_storage_api, redis_interface, helpers
from JupyRunner.core import scriptrunner as runner

from JupyRunner.client import api_accessor as capi

from JupyRunner.core.helpers import get_utcnow, make_zulustr, parse_zulutime, log, set_loglevel, get_primary_ip, load_config, get_db_url
from JupyRunner.core.helpers_mattermost import send_mattermost, LOGGING_EMOJIES

my_runner_id = os.environ.get('RUNNER_ID', None)

config = load_config()

run_directly = None

processes = {}



modules = [runner, filesys_storage_api]
for module in modules:
    module.setup(config)

for module in modules:
    module.start(config)




api = runner.api

dbserver_uri = get_db_url(config=config)
api_log = capi.ServerApi(dbserver_uri)

run_directly = config.get('procserver', {}).get('do_direct_running', 0)
user_info_verbosity = config.get('procserver', {}).get('user_info_verbosity', 0)

commit = runner.commit
set_prop_remote = runner.set_prop_remote

def get_script(script_id:int) -> schema.Script:
    if isinstance(script_id, str):
        script_id = int(script_id)
    return api.get(script_id)



rapi = redis_interface.RedisApi()
pubsub_run = rapi.subscribe_script_start()
pubsub_cancle = rapi.subscribe_script_cancle()
pubsub_prepare = rapi.subscribe_script_prepare()
timeout_redis = config.get('procserver', {}).get('timeout_redis', 0.1)

def get_scripts_redis(pubsub):
    script_ids = rapi.get_messages(pubsub, timeout_redis)
    script_ids = set(script_ids)
    if script_ids:
        chans = list(pubsub.channels)
        helpers.log.info(f'Redis PubSub: {chans=} Got N={len(script_ids)} --> {script_ids=}')

    scripts = [get_script(sid) for sid in script_ids]
    
    return [x for x in scripts if not x is None]

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

def finish(p, sid):
    log.info(f'{sid} DONE. returncode:{p.returncode}')
    retcode = p.poll()
    out, err = p.communicate()
    
    out = out.decode(sys.stdout.encoding)
    err = err.decode(sys.stderr.encoding)

    obj = get_script(sid)
    if retcode:
        obj.append_error_msg(err)
        log.error('ERROR: ' + err)
        log.debug('setting status: FAILED...' )
        obj = set_prop_remote(sid, status = schema.STATUS.FAILED, errors = obj.errors)

        s = ''
        s += f'\nFAILED on processing for script {sid}'
        s += f'\nError Message: ```{str(err)}```'
        s += f'\nSTATUS NEW: **FAILED**'
        send_mattermost(s, emoji=LOGGING_EMOJIES.FAIL)

        filename_without_extension = os.path.splitext(os.path.basename(obj.script_out_path))[0]

        try:
            if user_info_verbosity > 0: 
                api_log.user_info('Procserver: ' + s, color='red', script_id=sid, script_uid=filename_without_extension, device_id=obj.device_id)
            
        except Exception as err:
            pass
        

    else:
        try:
            if user_info_verbosity > 0:
                api_log.user_info('Procserver: FINISHED', color='grey', script_id=sid, script_uid=filename_without_extension, device_id=obj.device_id)
        except Exception as err:
            pass

    return sid


def start_job(sid):

    assert not sid in processes, f'cannot start job {sid=} since it is still running!'
    assert sid, 'need to give an id!'
    run_script_path = config['procserver']['run_script_path']
    
    cmds = [run_script_path, '--id', str(sid)]
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
        
    processes[sid] = p

def cancle_job(sid):
    if not test_is_running(sid):
        return 404, {'ERROR': 'no such job found within running jobs'}
    else:
        p = processes[sid]
        p.terminate()
        p.wait(timeout=config['procserver']['terminate_timeout_sec'])
        p.kill()
        out, err = p.communicate()
        out = out.decode(sys.stdout.encoding)
        err = err.decode(sys.stderr.encoding)
        
        obj = get_script(sid)
        obj.append_error_msg(err)
        obj = set_prop_remote(obj, status = schema.STATUS.CANCELLED, errors = obj.errors)
        
        del processes[sid]



def tick_awaiting_check(do_qry):
    # initial checks
    log.debug(f'tick_awaiting_check...')

    scripts = get_scripts_redis(pubsub_prepare)

    if do_qry:
        stati = [schema.STATUS.INITIALIZING, schema.STATUS.AWAITING_CHECK]
        scripts += api.qry(stati=stati)

    log.debug(f'got N={len(scripts)} scripts which need attention...')

    for script in scripts:
        try:
            log.info(f'CHECKING for {script.id=} --> {script.status=} | {script.script_out_path}')

            
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

        log.info(f'DONE CHECKING with {script.id=} --> {script.status=} | {script.script_out_path}')

        script = commit(script)
        # if sufficiently close start time
        if script.start_condition <= (get_utcnow() + datetime.timedelta(seconds=2)):
            # start direct
            rapi.trigger_script_start(script.id)
        else:
            # schedule for later
            rapi.schedule_script(script.id, script.start_condition)


def tick_cancelling(do_qry):
    log.debug(f'tick_cancelling...')
    

    scripts = get_scripts_redis(pubsub_cancle)

    if do_qry:
        # initial checks
        stati = [schema.STATUS.CANCELLING]
        scripts += api.qry(stati=stati)

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

        log.info(f'DONE CHECKING  with {script.id=} --> {script.status=} | {script.script_out_path}')
        
def tick_housekeeping(do_qry):
    log.debug(f'tick_housekeeping...')
    # initial checks
    if do_qry:
        stati = [schema.STATUS.RUNNING]
        scripts = api.qry(stati=stati)

        log.debug(f'got N={len(scripts)} scripts which need attention...')

        for script in scripts:
            stat = ''
            try:
                if not test_is_running(script.id):
                    stat = schema.STATUS.FAULTY
            except Exception as err:
                script.append_error_msg(str(err))
                log.error('ERROR: ' + str(err))
                stat = schema.STATUS.FAULTY
            
            if stat:
                log.debug('setting status... ' + stat)
                script = set_prop_remote(script, status=stat, errors=script.errors)
            log.info(f'DONE CHECKING  with {script.id=} --> {script.status=} | {script.script_out_path}')
                



def tick_cleanup(do_qry):
    log.debug(f'tick_cleanup...')
    # clean up if finished
    to_remove = []
    for script_id, p in processes.items():
        try:
            log.debug(f'{script_id=}, process: {p=}')

            if not test_is_running(script_id):
                log.info(f'CLEANING UP PROCESSES for script {script_id}, {p}')
                k = finish(p, script_id)
                to_remove.append(k)
                log.info(f'DONE CLEANING script {script_id}, {p}')
            else:
                log.debug(f'... still running')
                # p = subprocess.Popen(cmds, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                # log.debug(f'{p.stdout.readlines()=}')
                # log.debug(f'{p.stderr.readlines()=}')

        except Exception as err:
            obj = get_script(script_id)
            obj.append_error_msg(err_msg=str(err))
            log.exception(f'ERROR while cleaining up {key}, {p}')
            log.exception('ERROR: ' + str(err))
            set_prop_remote(obj, status=schema.STATUS.FAULTY, errors=obj.errors)
    
    for key in to_remove:
        removed = processes.pop(key)
        log.debug('removed: ' + str(removed) )
        

def tick_start(do_qry):

    log.debug(f'tick_start...')

    scripts = get_scripts_redis(pubsub_run)
    
    if do_qry:
        stati = [schema.STATUS.STARTING, schema.STATUS.WAITING_TO_RUN]
        scripts += api.qry(stati=stati)

    log.debug(f'got N={len(scripts)} scripts which need attention...')
    for script in scripts:
        try:
            key = script.id

            if not test_is_running(key) and \
                script.test_for_start_condition() and \
                    (test_shall_I_run_this_script(script) or test_shall_I_run_this_script(script, by_ip=True)):
                
                log.info(f'STARTING PROCESSING with {script.id=} --> {script.status=} | {script.script_out_path}')
                log.debug('setting status... ' + schema.STATUS.STARTING)
                script = set_prop_remote(script, status = schema.STATUS.STARTING)
                assert script.status == schema.STATUS.STARTING
                
                if run_directly:
                    runner.run_script(script.id)
                    log.info('DONE RUNNING with ')
                    runner.init_follow_up_script(script)
                    
                else:
                    start_job(script.id)
                    log.info(f'DONE STARTING with {script.id=} --> {script.status=} | {script.script_out_path}')
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

    

def tick(do_qry=False):
    log.debug(f'tick... ')
    tick_awaiting_check(do_qry)
    tick_cancelling(do_qry)
    tick_cleanup(do_qry)
    tick_housekeeping(do_qry)
    tick_start(do_qry)
    log.debug(f'tick... DONE')

def startup_testrun():
    dummy_device = runner.device_api.get('dummy_device')
    if dummy_device is None:
        dummy_device = schema.Device(id='dummy_device', address='http://localhost:8080', connection_protocol='http', comments='a dummy device for testing')
        dummy_device = runner.device_api.put(dummy_device)

    p = '/home/jovyan/99_startup_testscript.ipynb'
    assert os.path.exists(p), 'startup testscript is missing! >> '  + p
    new_path = filesys_storage_api.default_dir_repo + '/' + os.path.basename(p)
    shutil.copy(p, new_path)

    startup_script = runner.api.post({'script_in_path': new_path, 'device_id': 'dummy_device'})
    assert startup_script, 'error starting a testscript!'

    # papermill "/home/jovyan/shared/repos/99_startup_testscript.ipynb" "/home/jovyan/work/test.ipynb" -p "path_to_libs" "/home/jovyan/shared/libs/"

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
    if isinstance(procserver_info.time_initiated, str):
        procserver_info.time_initiated = parse_zulutime(procserver_info.time_initiated)
    if isinstance(procserver_info.last_time_changed, str):
        procserver_info.last_time_changed = parse_zulutime(procserver_info.last_time_changed)

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
    t_interval = config.get('procserver', {}).get('t_interval', 60)
    t_sleep = config.get('procserver', {}).get('t_sleep', 1)
    t_info = config.get('procserver', {}).get('t_info', 60*60)

    i = 0
    log.info(f'procserver waiting {t_interval/4} sec before starting...')
    time.sleep(t_interval/4) # to have the DB up and running
    log.info(f'pinging server at "{api.base_url}"...')

    assert runner.api_interface.ping(), f'pinging {runner.api_interface.url=} failed!'
    log.info('ping OK!')

    startup_info()
    
    startup_testrun()
    tlast_info = -1
    tlast_query = -1


    while(1):

        try:
            now = time.time()
            if (now - tlast_info) > t_info:
                tlast_info = now
                log.info('procserver is still alive!')
                update_ticker(t_sleep)

            if (now - tlast_query) > t_interval:
                tlast_query = now
                do_qry = True
            else:
                do_qry = False

            tick(do_qry)
            i += 1

        except Exception as err:
            log.error(err)
            traceback.print_exception(err)

        time.sleep(t_sleep)

if __name__ == '__main__':
    log.info('STARTING procserver!')

    if (len(sys.argv) >1 and 'debug' in sys.argv[-1].lower()):
        log.setLevel('DEBUG')

        dc = {
            # "script_in_path": r"C:\Users\tglaubach\repos\jupyter-script-runner\src\scripts\00_example_script.ipynb".replace('\\', '/'),
            #"script_in_path": r"C:\Users\tglaubach\repos\jupyter-script-runner\src\scripts\02_example_functional_test.ipynb".replace('\\', '/'),
            "script_in_path": r"home/jovyan/shared/repos/99_startup_testscript.ipynb",
            "script_params_json": { "do_upload": 1 }
            # ... other script attributes
        }
        print('post!')

        api.post(dc)
        print('post-done...')
        tick()

    elif len(sys.argv) > 1:
        my_runner_id = sys.argv[-1]
        run()
    else:
        run()