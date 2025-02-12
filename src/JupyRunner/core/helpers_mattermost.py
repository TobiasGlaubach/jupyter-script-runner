
import requests
import socket
import enum
import json
import os
import shlex

from JupyRunner.core.helpers import get_utcnow, make_zulustr, parse_zulutime, log
from JupyRunner.core import schema

from JupyRunner.core import db_interface as dbi
from JupyRunner.core import helpers_userfeedback as usr
from JupyRunner.core import helpers


url = None
dbserver_uri = None
incoming_token = None

def setup(config):
    global url, incoming_token, dbserver_uri
    url = os.environ.get('MATTERMOST_URL', '')
    incoming_token = os.environ.get('MATTERMOST_INCOMING', '')
    dbserver_uri = helpers.get_db_url(with_port=True, with_http=True, config=config)

def start(config):
    pass


class LOGGING_EMOJIES(enum.auto):
    WARNING = ':warning: '
    FAIL = ':x: '
    SUCCESS = ':white_check_mark: '
    INFO = ':information_source: '
    EMPTY = ''


def send_mattermost(subject, emoji = ''):

    try:

        #s = f'{emoji}```{make_zulustr(get_utcnow())} | {send_mattermost.hostname} | {send_mattermost.ip} | ``` '
        s = f'{emoji}```{make_zulustr(get_utcnow())} ``` '
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
    
    
# send_mattermost.hostname = socket.gethostname()
# send_mattermost.ip = socket.gethostbyname(socket.gethostname())



async def handle_webhook_request(data, feedback_requests, _user_feedback_reply) -> dict:
    try:
        if data.get('trigger_word') in '#open #status'.split():
            

            args = data.get('text').split()
            r = [feedback_requests.get(id, None) for id in feedback_requests]
            r = '\n'.join([rr.make_markdown_li() for rr in r if rr.request_type != 'info'])
            stati = [s for s in schema.STATUS if not s in [schema.STATUS.FAULTY, schema.STATUS.FAILED, schema.STATUS.CANCELLED, schema.STATUS.ABORTED, schema.STATUS.FAULTY, schema.STATUS.FINISHED]]
            res = dbi.qry_scripts(stati=stati)
            make_markdown = lambda script: f'1. {script.get_device_link_md()} | {script.get_link_md()} | {script.get_showpath_md()} | STATUS=**{script.status}**'
            pathes = '\n'.join([make_markdown(r) for r in res])
            if not pathes:
                pathes = 'None'
            if not r:
                r = 'None'

            text = f"\n#### Running Scripts:\n\n{pathes}\n\n#### Feeback Requests:\n\n{r}\n"
        elif data.get('trigger_word') == '#reply':
            args = shlex.split(data.get('text'))
            args.pop(0)
            reply_for = args.pop(0, '')
            open_requests = {**{v.get_id_short():v for k, v in feedback_requests.items()}, **{v.id:v for k, v in feedback_requests.items()}}
            req = open_requests.get(reply_for, None)

            if not req is None:
                reply_text = args.pop(0, '')
                
                client = str(data.get('user', 'unknown')) + ' from mattermost channel ' + str(data.get('channel_name', 'unknown'))
                reply = usr.UserFeedbackReply(id=req.id, message=str(reply_text), response_type=req.request_type, files={}, client=client)

                assert reply.response_type == req.request_type, f'expected was feedback of type: {req.request_type} but given was response of type: {reply.response_type}'
                could_parse, errors = reply.parse(allow_confirm=True)
                if could_parse and not errors:
                    res, reply, input_data, req = await _user_feedback_reply(reply)
                    text = f'Found Reply for feedback request "{reply_for}" ({req.request_type}): {reply_text} --> success={reply.success} value={reply.value}'
                else:
                    text = f'Found Reply for feedback request "{reply_for}" ({req.request_type}): {reply_text} --> ERROR: {errors}'
            else:    
                text = f"could not match any reply for: \"{data.get('text')}\""

        elif data.get('trigger_word') == '#s' or data.get('trigger_word') == '#exp' or data.get('trigger_word') == '#script':
            args = shlex.split(data.get('text'))
            args.pop(0)
            text = []

            for id_ in args:
                obj = dbi.get(schema.Script, int(id_))
                if not obj:
                    text.append(f'## Script "{id_}"\n\n **ERROR**: The script with {id_=} was not found!')
                else:
                    text.append(obj.to_md(base_url=dbserver_uri))
            text = '\n\n'.join(text)
        elif data.get('trigger_word') == '#d' or data.get('trigger_word') == '#device':
            args = shlex.split(data.get('text')) 
            args.pop(0)
            text = []

            for id_ in args:
                obj = dbi.get(schema.Device, id_)
                if not obj:
                    text.append(f'## Device "{id_}"\n\n **ERROR**: The device with {id_=} was not found!')
                else:
                    text.append(obj.to_md(base_url=dbserver_uri))

            text = '\n\n'.join(text)
        elif data.get('trigger_word') == '#result' or data.get('trigger_word') == '#datafile':
            args = shlex.split(data.get('text'))  
            args.pop(0)
            text = []

            for id_ in args:
                obj = dbi.get(schema.Datafile, int(id_))
                if not obj:
                    text.append(f'## Datafile "{id_}"\n\n **ERROR**: The datafile with {id_=} was not found!')
                else:
                    text.append(obj.to_md(base_url=dbserver_uri))
            text = '\n\n'.join(text)
        elif data.get('trigger_word') == '#l' or data.get('trigger_word') == '#list' or data.get('trigger_word') == '#lastn' or data.get('trigger_word') == '#last':
            args = shlex.split(data.get('text'))  
            args.pop(0)
            N = int(next(iter(args), 5))
            scripts = dbi.get_last_n(schema.Script, N)
            table_header = "| ID | Script Out Path | Status | Comments |\n| --- | --- | --- | --- |\n"
            table_rows = ""
            for script in scripts:
                comments = helpers.limit_len(script.comments, 50).replace('\n', ' ')
                script_out_path_link = f"[{os.path.basename(script.script_out_path)}]({dbserver_uri}/show/{script.script_out_path})"
                table_rows += f"| {script.id} | {script_out_path_link} | {script.status} | {comments} |\n"
            text = f'## Last {N=} Scripts\n\n' + table_header + table_rows

        elif data.get('trigger_word') == '#set' or data.get('trigger_word') == '#edit' or data.get('trigger_word') == '#update':
            args = shlex.split(data.get('text'))
            args.pop(0)
            clsname = args.pop(0)
            whats = {
                'script': (int, schema.Script),
                'device': (str, schema.Device),
                'datafile': (int, schema.Datafile)
            }

            type_id, type_cls = whats.get(clsname, (None, None))
            if not type_cls:
                return f':x: :fire: ERROR: Can only edit script, device, or datafile \n\n```\n{json.dumps(data, indent=2)}\n```'
            
            id_ = type_id(args.pop(0))
            prop = args.pop(0)
            val = args.pop(0)
            obj = dbi.set_property(type_cls, id_, **{prop:val})
            text = f':white_check_mark: SUCCESS: updated {clsname}[{id_}].{prop} = {val} (with {type(val)=})\n new object below:'
            text += '\n\n---\n\n' + obj.to_md(dbserver_uri)
            
        elif data.get('trigger_word') == '#help' or data.get('trigger_word') == '#h':
            text = ''' ## Webhook API for JupyRun: 

Available commands are:
- `#script {script_id:int}` -> show info about the script with a given ID
- `#device {device_id:str}` -> show info about the device with a given string ID
- `#datafile {datafile_id:int}` -> show info about the datafile_id with a given ID
- `#lastn {n:int}` OR `#list {n:int}` -> show info about the last N scripts in table form
- `#set {object_type:str} {object_id:int|str} {property_name:str} {property_value:Any}` will retrieve the specified object, parse the given inputs to the needed types and set the given property accordingly. Works for `object_type` `script`, `device`, and `datafile`. e.G. `#set script 1 status FAULTY`
- `#status` -> shows what user feedback requests are currently open
- `#reply {feedback_id} "{Text}"` -> answers on a currently open user feedback request
'''

        else:
            text = f':x: :fire: ERROR: unhandled case!\n\n```\n{json.dumps(data, indent=2)}\n```'
    
    except Exception as err:
        text = f':x: :fire: ERROR: {err} :fire: :x:'
    
    return text

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
