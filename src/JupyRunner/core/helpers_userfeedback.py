

import hashlib
import os
import time
from pydantic import BaseModel


from JupyRunner.core import db_interface as dbi
from JupyRunner.core import schema, helpers


class UserFeedbackRequest(BaseModel):
    message: str
    request_type: str
    id: str
    script_id: int|None = None
    script_name: str|None = None
    script_state: str|None = ''
    device_id: str|None = None
    timestamp: float|None = None
    kwargs: dict|None = None
    handled: int |None = None

    
    def populate_empty_fields(self):
        self = self
        script = None

        if not self.timestamp or self.timestamp <= 0:
            self.timestamp = time.time()

        if not self.script_name and self.script_id:
            script = self.get_script()
            filename_without_extension = os.path.splitext(os.path.basename(script.script_out_path))[0]
            self.script_name = filename_without_extension
        
        if not self.device_name and self.script_id:
            script = self.get_script() if not script else script
            self.device_id = script.device_id  

        if not self.device_name:
            self.device_name = 'no_device'

        if not self.script_id:
            self.script_id = 0
        
        if not self.script_name:
            self.script_name = f'loose_request_{self.id}'

        return self
    
    def get_script(self) -> schema.Script:
        if self.script_id:
            return dbi.get(schema.Script, self.script_id)
        else:
            return None
    
    def update_state(self):
        script = self.get_script()
        if script:
            self.script_state = script.status.name
        else:
            self.script_state = ''
        return self

    def get_script_uid(self) -> str:
        return f'loose_request_{self.id}' if not self.script_name else self.script_name


    def get_id_short(self) -> str:
        # Create a hash object using the SHA-256 algorithm
        hash_object = hashlib.sha256()
        hash_object.update(self.id.encode())
        hex_digest = hash_object.hexdigest()
        return hex_digest[-8:] # only last 8 bytes
        
    def make_markdown_li(self):
        s = f'''1. {self.get_id_short()} (`{self.id}`)
   - **Request Type**: {self.request_type}
   - **Message**: {helpers.limit_len(self.message, 200)}'''
        
        if self.script_id:
            s += f'\n   - **Script ID**: {helpers.limit_len(self.script_id, 200)}'
        
        if self.device_id:
            s += f'\n   - **Device ID**: {helpers.limit_len(self.device_id, 200)}'
        return s    

    def match_script(self, script):
        if not (self.script_name or self.script_id):
            return True
        if self.script_name is not None and self.script_name == os.path.basename(script.script_out_path):
            return True
        if self.script_id is not None and self.script_id == script.id:
            return True
        return False


class UserFeedbackReply(BaseModel):
    id: str
    message: str
    response_type: str
    value: float|int|None|str = None
    files: dict[str, str]|None = None
    client: str
    success : bool | int | None = None
    timestamp : int | float | None = None
    
    
    def parse(self, allow_confirm=True):
        
        self = self
        allowed = 'confirm file files picture pictures text int float'.split()
        assert self.response_type in allowed, f'the given response {self.response_type} is not in the allowed types: {allowed=}'

        if not self.timestamp:
            self.timestamp = time.time()

        msg = self.message.strip()
        tp = self.response_type
        if tp == 'confirm':
            if allow_confirm and self.success is None and msg:
                self.success = msg.lower() in '1 true ok yes ja'.split()
            return True, ''
        elif tp == 'text': 
            self.value = msg.strip()
            self.success = True if self.value else False
            return self.success, ('Input string can not be empty!' if not self.success else '')
        elif tp == 'int':
            self.value = helpers.parse_number(self.message, int)
            self.success = not self.value is None
            return self.success, (f'The input {msg=} could not be parsed to the expected int type' if not self.success else '')
        elif tp == 'float':
            self.value = helpers.parse_number(self.message, float)
            self.success = not self.value is None
            return self.success, (f'The input {msg=} could not be parsed to the expected float type' if not self.success else '')
        elif tp in 'files picture pictures'.split():
            return False, 'Can not upload files using webhooks!'
        else:
            return False, 'unknown type!'

    def get_feedback_string(self, multiline = True):
        feedback = f'Request for "{self.response_type}" with prompt "{helpers.limit_len(self.message, 20)}" answered by: {self.client}'
        if self.success:
            feedback += '\n|> Successfully handled request'
            if self.message: 
                message = self.message
                feedback += f'\n|> With {message=}'

            for filename, b64_str in self.files.items():
                feedback += f'\n|> With filename {filename} (N={len(b64_str)})'
        else:
            feedback += "\n|> Cancelled by User"
        
        if not multiline:
            return feedback.replace("\n|> ", "--> ")
        else:
            return feedback

    def to_dict(self, multiline=False):
        data = {k:v for k, v in self.__dict__.items()}
        data['feedback_info'] = self.get_feedback_string(multiline)
        if not data['timestamp']: 
            data['timestamp'] = time.time()
        return data
    
    def mark_request_handled(self, req, feedback_str=''):
        req.handled = 1
        if req.kwargs is None:
            req.kwargs = {}
        req.kwargs['color'] = 'green' if self.success else 'red'
        req.message = feedback_str if feedback_str else self.get_feedback_string()
        return req