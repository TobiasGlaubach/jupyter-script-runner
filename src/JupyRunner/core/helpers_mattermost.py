
import requests
import socket

from JupyRunner.core.helpers import get_utcnow, make_zulustr, parse_zulutime, log

url = None


def setup(config):
    global url
    url = config['globals']['mattermost_uri']
    

def start(config):
    pass

def send_mattermost(subject):

    try:


        s = f'```{make_zulustr(get_utcnow())} | {send_mattermost.hostname} | {send_mattermost.ip} | ```'
        txt = s + subject

        if not url:
            log.error('send_mattermost not sending text, since no URL given')
            log.info('Mattermost Message: ' + txt)
        else:
            headers = {'Content-Type': 'application/json',}
            dc = { "text": txt}

            response = requests.post(url, headers=headers, json=dc) 

            if response.status_code != 200:
                log.error(f'send_mattermost failed with status_code: {response.status_code} | text: {response.text}')

    except Exception as err:
        log.error(f'send_mattermost failed with exception: {err.__repr__()}')
    
send_mattermost.hostname = socket.gethostname()
send_mattermost.ip = socket.gethostbyname(socket.gethostname())


if __name__ == '__main__':
    send_mattermost('This is a test message')

    out_path = 'some_path'
    script_name = 'some_script'
    id = 42
    eid = 142

    err = 'This is a test error'

    s = ''
    s += f'\nFAILED on post processing for result {id} experiment {eid}'
    s += f'\n-out_path = ```{out_path}```'
    s += f'\n-script_name = ```{script_name}```'
    s += f'\nError Message: ```{str(err)}```'
    s += f'\nSTATUS NEW: **POST_PROC_FAILED**'

    send_mattermost(s)
