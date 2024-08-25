
#!/usr/bin/python3
""" 
the processing core to run jupyter notebooks in papermill
"""

import subprocess

import sys, os
import time

import yaml

if __name__ == '__main__':
    # add to path for testing
    import sys, inspect, os
    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
    parent_dir = os.path.dirname(os.path.dirname(current_dir))
    sys.path.insert(0, parent_dir)

from JupyRunner.core import schema, db_interface, scriptscript
from JupyRunner.core.helpers import get_utcnow, make_zulustr, parse_zulutime, log
from JupyRunner.core.helpers_mattermost import send_mattermost



config =  None

processes = {}

with open('config.yaml', 'r') as fp:
    config = yaml.safe_load(fp)

assert os.path.exists(config.get('db', {})['filepath']), 'the database for the procserver does not exist!'
db_interface.setup(config)

def get_script(script_id:int) -> schema.Script:
    if isinstance(script_id, str):
        script_id = int(script_id)
    return db_interface.get(schema.Script, script_id)
    
def commit(script):
    db_interface.commit(script)


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
        obj.append_err_msg(err)
        log.debug('ERROR: ' + err)
        log.debug('setting status: FAILED...' )
        obj.status = schema.STATUS.FAILED
        commit(obj)

        s = ''
        s += f'\nFAILED on processing for script {id}'
        s += f'\nError Message: ```{str(err)}```'
        s += f'\nSTATUS NEW: **FAILED**'
        send_mattermost(s)

    return id


def start_job(id):

    assert id not in processes, f'cannot start job {id=} since it is still running!'

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
        obj.append_err_msg(err)
        obj.status = schema.STATUS.CANCELLED
        commit(obj)
        
        del processes[id]



def tick_awaiting_check():
    # initial checks
    stati = [schema.STATUS.AWAITING_CHECK]
    with db_interface.Session(db_interface.engine) as session:
        query = db_interface.select(schema.Script).where(schema.Script.status.in_(stati))
        scripts = session.exec(query).all()

        for script in scripts:
            try:
                log.info('CHECKING for ' + str(script))
                log.debug(f'   FROM: {script.script_in_path}')
                log.debug(f'     TO: {script.script_out_path}')
                
                log.debug('checking...')
                script.check()
                scriptscript.pre_test(script)
                stat = schema.STATUS.WAITING_TO_RUN
            except Exception as err:
                script.append_err_msg(str(err))
                log.debug('ERROR: ' + str(err))
                stat = schema.STATUS.FAULTY
            
            log.debug('setting status... ' + stat)
            script.status = stat
            session.add(script)

            log.info('DONE CHECKING with ' + str(script))

        session.commit()
    

def tick_cancelling():
    # initial checks
    stati = [schema.STATUS.CANCELLING]
    with db_interface.Session(db_interface.engine) as session:
        query = db_interface.select(schema.Script).where(schema.Script.status.in_(stati))
        scripts = session.exec(query).all()

        for script in scripts:
            try:
                if test_is_running(script.id):
                    cancle_job(script.id)
            except Exception as err:
                script.append_err_msg(str(err))
                log.debug('ERROR: ' + str(err))
                stat = schema.STATUS.FAULTY
            
            log.debug('setting status... ' + stat)
            script.status = stat
            session.add(script)

            log.info('DONE CHECKING with ' + str(script))
            
        session.commit()



def tick_cleanup():
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
            obj.append_err_msg(err_msg=str(err))
            log.exception(f'ERROR while cleaining up {key}, {p}')
            log.exception('ERROR: ' + str(err))
            obj.status=schema.STATUS.FAULTY
            commit(obj)
    
    for key in to_remove:
        removed = processes.pop(key)
        log.debug('removed: ' + str(removed) )
        

def tick_start():

    stati = [schema.STATUS.STARTING, schema.STATUS.WAITING_TO_RUN]

    with db_interface.Session(db_interface.engine) as session:
        query = db_interface.select(schema.Script).where(schema.Script.status.in_(stati))
        scripts = session.exec(query).all()

        for script in scripts:
            try:
                
                key = script.id
                if not test_is_running(key) and script.test_for_start_condition():
                    log.info('STARTING PROCESSING for ' + str(script))
                    start_job(script.id)
                    log.info('DONE STARTING with ' + str(script))
                else:
                    log.debug('test_is_running:          ' + str(test_is_running(key)))
                    log.debug('test_for_start_condition: ' + str(script.test_for_start_condition()))

            except Exception as err:
                script.append_err_msg(str(err))
                log.debug('ERROR: ' + str(err))
                stat = schema.STATUS.FAULTY
            
            log.debug('setting status... ' + stat)
            script.status = stat
            session.add(script)

            log.info('DONE CHECKING with ' + str(script))

        session.commit()
    

def tick():
    
    tick_awaiting_check()
    tick_cancelling()
    tick_cleanup()
    tick_start()

def update_ticker():
    procserver_tlast = db_interface.get(schema.ProjectVariable, 'procserver_tlast')
    if procserver_tlast is None:
        procserver_tlast = schema.ProjectVariable(id='procserver_tlast', data_json={'time': ''})
    procserver_tlast.data_json['time'] = get_utcnow()
    commit(procserver_tlast)

def run():
    log.info('procserver starting up!')
    t_sleep = config.get('procserver', {}).get('t_interval', 60)
    
    i = 0
    while(1):
        try:
            if i % 100 == 0:
                log.info('procserver is still alive!')
                update_ticker()

            tick()

        except Exception as err:
            log.error(err)

        time.sleep(t_sleep)

if __name__ == '__main__':
    tick()